"""Tutor conversations: create and read them, and run a turn that stores what was said.

Every function takes ``user_id`` and filters on it: another user's module, topic, study
session or conversation is ``NotFound``, exactly like a missing one.

A turn is two steps, so the HTTP layer can still answer 404 before it starts streaming:
1. ``prepare_message`` finds the conversation, retrieves the sources, builds the prompt,
   and stores the student's question.
2. ``run_turn`` streams the answer and stores it: ``complete``, ``truncated``, ``failed``
   (with whatever text came first), or ``stopped`` when the student left part-way.
"""

import asyncio
import itertools
import time
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass

import anyio
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.client import LLMClient, TextDelta
from app.core.config import Settings
from app.models import Conversation, Message, MessageSource, StudySession, Topic
from app.schemas.tutor import (
    ConversationCreate,
    DeltaEvent,
    DoneEvent,
    ErrorEvent,
    MessageCreate,
    SourcesEvent,
)
from app.services.academics.modules import get_module
from app.services.errors import NotFound
from app.services.search.embedding import Embedder
from app.services.tutor.citations import parse_citations
from app.services.tutor.prompts import Exchange
from app.services.tutor.retrieval import PreviousSource
from app.services.tutor.turn import HISTORY_EXCHANGES, Answer, Turn, answer, build_turn

# Modes that work on the last answer's sources rather than searching again.
FOLLOW_UP_MODES = ("explain_differently", "example")
# Answers that count as history for the next question (a failed or stopped one doesn't).
HISTORY_STATUSES = ("complete", "truncated")


async def create_conversation(
    session: AsyncSession, module_id: uuid.UUID, data: ConversationCreate, *, user_id: uuid.UUID
) -> Conversation:
    await get_module(session, module_id, user_id=user_id)
    topic_id = data.topic_id
    if data.study_session_id is not None:
        study = await session.scalar(
            select(StudySession).where(
                StudySession.id == data.study_session_id,
                StudySession.user_id == user_id,
                StudySession.module_id == module_id,
            )
        )
        if study is None:
            raise NotFound("Study session")
        topic_id = topic_id or study.topic_id
    if data.topic_id is not None:
        found = await session.scalar(
            select(Topic.id).where(
                Topic.id == data.topic_id, Topic.user_id == user_id, Topic.module_id == module_id
            )
        )
        if found is None:
            raise NotFound("Topic")
    conversation = Conversation(
        user_id=user_id,
        module_id=module_id,
        study_session_id=data.study_session_id,
        topic_id=topic_id,
    )
    session.add(conversation)
    await session.commit()
    return conversation


@dataclass(frozen=True)
class ConversationView:
    conversation: Conversation
    messages: list[Message]


async def get_conversation(
    session: AsyncSession, conversation_id: uuid.UUID, *, user_id: uuid.UUID
) -> ConversationView:
    conversation = await find_conversation(session, conversation_id, user_id=user_id)
    messages = list(
        await session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id, Message.user_id == user_id)
            .options(selectinload(Message.sources))
            .order_by(Message.position)
            .execution_options(populate_existing=True)
        )
    )
    return ConversationView(conversation, messages)


async def list_conversations(
    session: AsyncSession,
    module_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
    study_session_id: uuid.UUID | None = None,
) -> list[ConversationView]:
    """The module's conversations, newest first, optionally only one study session's.

    ``NotFound`` if the module isn't the user's. A session ID that isn't theirs simply
    matches nothing, like a missing one.
    """
    await get_module(session, module_id, user_id=user_id)
    query = select(Conversation.id).where(
        Conversation.module_id == module_id, Conversation.user_id == user_id
    )
    if study_session_id is not None:
        query = query.where(Conversation.study_session_id == study_session_id)
    ids = list(
        await session.scalars(query.order_by(Conversation.created_at.desc(), Conversation.id))
    )
    return [await get_conversation(session, found, user_id=user_id) for found in ids]


async def find_conversation(
    session: AsyncSession, conversation_id: uuid.UUID, *, user_id: uuid.UUID
) -> Conversation:
    conversation = await session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user_id
        )
    )
    if conversation is None:
        raise NotFound("Conversation")
    return conversation


async def recent_exchanges(
    session: AsyncSession, conversation_id: uuid.UUID, *, user_id: uuid.UUID
) -> list[Exchange]:
    """The last ``HISTORY_EXCHANGES`` questions that got an answer, oldest first.

    Quizzes aren't history: their text is only a summary, and the questions are the
    student's to answer, not context for the next one.
    """
    rows = list(
        await session.execute(
            select(Message.role, Message.text, Message.status, Message.mode)
            .where(Message.conversation_id == conversation_id, Message.user_id == user_id)
            .order_by(Message.position)
        )
    )
    exchanges: list[Exchange] = []
    for (role, question, _, mode), (next_role, reply, status, _) in itertools.pairwise(rows):
        if (
            role == "user"
            and next_role == "assistant"
            and mode != "quiz"
            and status in HISTORY_STATUSES
            and reply.strip()
        ):
            exchanges.append(Exchange(question, reply))
    return exchanges[-HISTORY_EXCHANGES:]


async def add_message(session: AsyncSession, message: Message) -> Message:
    """Store a message at the end of its conversation."""
    last = await session.scalar(
        select(func.max(Message.position)).where(
            Message.conversation_id == message.conversation_id,
            Message.user_id == message.user_id,
        )
    )
    message.position = 0 if last is None else last + 1
    session.add(message)
    await session.commit()
    return message


async def previous_sources(
    session: AsyncSession, conversation_id: uuid.UUID, *, user_id: uuid.UUID
) -> list[PreviousSource]:
    """The sources of the conversation's last answer that had any, S1 first."""
    message_id = await session.scalar(
        select(Message.id)
        .where(
            Message.conversation_id == conversation_id,
            Message.user_id == user_id,
            Message.role == "assistant",
            exists().where(MessageSource.message_id == Message.id),
        )
        .order_by(Message.position.desc())
        .limit(1)
    )
    if message_id is None:
        return []
    rows = await session.execute(
        select(
            MessageSource.label,
            MessageSource.chunk_id,
            MessageSource.material_id,
            MessageSource.page_number,
        )
        .where(MessageSource.message_id == message_id, MessageSource.user_id == user_id)
        .order_by(MessageSource.rank)
    )
    return [PreviousSource(*row) for row in rows]


async def last_question(
    session: AsyncSession, conversation_id: uuid.UUID, *, user_id: uuid.UUID
) -> str | None:
    """The conversation's last question asked in answer mode, if any."""
    found: str | None = await session.scalar(
        select(Message.text)
        .where(
            Message.conversation_id == conversation_id,
            Message.user_id == user_id,
            Message.role == "user",
            Message.mode == "answer",
        )
        .order_by(Message.position.desc())
        .limit(1)
    )
    return found


@dataclass(frozen=True)
class PreparedTurn:
    user_id: uuid.UUID
    conversation_id: uuid.UUID
    turn: Turn


async def prepare_message(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    data: MessageCreate,
    *,
    user_id: uuid.UUID,
    embedder: Embedder,
    settings: Settings,
) -> PreparedTurn:
    """Find the conversation, build the turn and store the question. ``NotFound`` if the
    conversation isn't the user's."""
    started = time.monotonic()
    conversation = await find_conversation(session, conversation_id, user_id=user_id)
    history = await recent_exchanges(session, conversation.id, user_id=user_id)
    # A follow-up mode works on the last answer's sources; a new question searches with the
    # previous question as context (ARCHITECTURE "AI integration": the tutor turn).
    reuse = (
        await previous_sources(session, conversation.id, user_id=user_id)
        if data.mode in FOLLOW_UP_MODES
        else []
    )
    previous_question = (
        await last_question(session, conversation.id, user_id=user_id)
        if data.mode == "answer"
        else None
    )
    turn = await build_turn(
        session,
        conversation.module_id,
        data.question,
        data.mode,
        user_id=user_id,
        topic_id=conversation.topic_id,
        history=history,
        embedder=embedder,
        settings=settings,
        started=started,
        previous_question=previous_question,
        reuse=reuse,
    )
    await add_message(
        session,
        Message(
            user_id=user_id,
            conversation_id=conversation.id,
            role="user",
            mode=data.mode,
            text=data.question,
            status="complete",
        ),
    )
    return PreparedTurn(user_id, conversation.id, turn)


async def _store_answer(
    session: AsyncSession, prepared: PreparedTurn, result: Answer, status: str
) -> Message:
    turn = prepared.turn
    message = Message(
        user_id=prepared.user_id,
        conversation_id=prepared.conversation_id,
        role="assistant",
        mode=turn.mode,
        text=result.text,
        status=status,
        model=result.model,
        first_token_ms=result.first_token_ms,
        total_ms=result.total_ms,
        unknown_citations=result.unknown_citations,
    )
    message.sources = [
        MessageSource(
            user_id=prepared.user_id,
            label=source.label,
            # Reused sources keep their labels, so the rank follows the label (S3 is 3).
            rank=int(source.label[1:]),
            chunk_id=source.chunk_id,
            material_id=source.material_id,
            material_title=source.material_title,
            page_number=source.page_number,
            page_title=source.page_title,
            cited=source.label in result.cited,
        )
        for source in turn.sources
    ]
    return await add_message(session, message)


async def run_turn(
    session: AsyncSession, prepared: PreparedTurn, *, client: LLMClient
) -> AsyncGenerator[SourcesEvent | DeltaEvent | DoneEvent | ErrorEvent]:
    """Stream the answer and store it; the last event is ``DoneEvent`` or ``ErrorEvent``.

    If the reader goes away (the client disconnected), the provider's stream is closed
    and what was said so far is stored as ``stopped``.
    """
    turn = prepared.turn
    parts: list[str] = []
    model: str | None = None
    first_token_ms: int | None = None
    events = answer(turn, client=client, user_id=prepared.user_id)
    result: Answer | None = None
    closed = False
    try:
        async for event in events:
            if isinstance(event, Answer):
                result = event
                break
            if isinstance(event, TextDelta):
                if first_token_ms is None:
                    first_token_ms = max(0, int((time.monotonic() - turn.started) * 1000))
                parts.append(event.text)
                model = event.model
                yield DeltaEvent(text=event.text)
            else:
                yield event
    except (GeneratorExit, asyncio.CancelledError):
        text = "".join(parts)
        citations = parse_citations(text, [s.label for s in turn.sources])
        stopped = Answer(
            status="stopped",
            text=text,
            model=model,
            first_token_ms=first_token_ms,
            total_ms=max(0, int((time.monotonic() - turn.started) * 1000)),
            cited=citations.cited,
            unknown_citations=citations.unknown,
        )
        # Shielded: while being cancelled, every other await would be cancelled too.
        with anyio.CancelScope(shield=True):
            await events.aclose()  # closes the provider's stream (logged as stopped)
            closed = True
            await _store_answer(session, prepared, stopped, "stopped")
        raise
    finally:
        if not closed:
            with anyio.CancelScope(shield=True):
                await events.aclose()
    assert result is not None
    message = await _store_answer(session, prepared, result, result.status)
    if result.status == "failed" or result.model is None:
        yield ErrorEvent(
            message_id=message.id,
            message=result.error or "The tutor couldn't answer.",
            retry_at=result.retry_at,
        )
        return
    yield DoneEvent(
        message_id=message.id,
        status="truncated" if result.status == "truncated" else "complete",
        model=result.model,
        first_token_ms=result.first_token_ms or 0,
        total_ms=result.total_ms,
        cited=result.cited,
        unknown_citations=result.unknown_citations,
    )
