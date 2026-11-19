"""The tutor: conversations, and answers streamed as server-sent events (ADR 0013)."""

import asyncio
import uuid
from collections.abc import AsyncIterable
from contextlib import aclosing
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.ai.client import get_llm_client
from app.api.deps import CurrentUser
from app.core.config import get_settings
from app.core.db import SessionDep
from app.schemas.tutor import (
    ConversationCreate,
    ConversationOut,
    DeltaEvent,
    DoneEvent,
    ErrorEvent,
    MessageCreate,
    MessageOut,
    QuizAnswersIn,
    SourcesEvent,
)
from app.services.search.embedding import get_embedder
from app.services.tutor.conversations import (
    ConversationView,
    PreparedTurn,
    create_conversation,
    get_conversation,
    list_conversations,
    prepare_message,
    run_turn,
)
from app.services.tutor.quiz import make_quiz, save_quiz_answers

router = APIRouter(tags=["tutor"])

EVENT_NAMES: dict[type, str] = {
    SourcesEvent: "sources",
    DeltaEvent: "delta",
    DoneEvent: "done",
    ErrorEvent: "error",
}


def _out(view: ConversationView) -> ConversationOut:
    return ConversationOut.model_validate(
        {
            "id": view.conversation.id,
            "module_id": view.conversation.module_id,
            "study_session_id": view.conversation.study_session_id,
            "topic_id": view.conversation.topic_id,
            "created_at": view.conversation.created_at,
            "messages": view.messages,
        }
    )


@router.post(
    "/modules/{module_id}/tutor/conversations",
    response_model=ConversationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create(
    module_id: uuid.UUID, data: ConversationCreate, session: SessionDep, user: CurrentUser
) -> ConversationOut:
    """Start a tutor conversation in the module, optionally for a study session and a topic.

    Without a topic, the session's topic is used. Retrieval boosts the topic's pages."""
    conversation = await create_conversation(session, module_id, data, user_id=user.id)
    return _out(await get_conversation(session, conversation.id, user_id=user.id))


@router.get("/modules/{module_id}/tutor/conversations", response_model=list[ConversationOut])
async def list_for_module(
    module_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
    study_session_id: uuid.UUID | None = None,
) -> list[ConversationOut]:
    """The module's tutor conversations, newest first, each with its messages.

    `?study_session_id=` keeps one session's (the tutor panel restores it after a reload).
    Another user's session ID gives `[]`, like a missing one."""
    views = await list_conversations(
        session, module_id, user_id=user.id, study_session_id=study_session_id
    )
    return [_out(view) for view in views]


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
async def read(
    conversation_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> ConversationOut:
    """The conversation with its messages, oldest first, and each answer's sources."""
    return _out(await get_conversation(session, conversation_id, user_id=user.id))


@router.post(
    "/conversations/{conversation_id}/quiz",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        503: {"description": "No AI model can take it now; Retry-After says when to try again"}
    },
)
async def quiz(conversation_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> MessageOut:
    """ "Quiz me": 3 multiple-choice questions on the last answer's sources (not streamed).

    The question ("Quiz me") and the answer are stored like any other turn; the answer is
    `failed` with a readable `text` when the AI's quiz couldn't be used. Questions whose
    sources weren't among the answer's are dropped, so there may be fewer than 3. 422 when
    nothing has been answered yet; 503 (with Retry-After) when the AI is busy."""
    message = await make_quiz(
        session, conversation_id, user_id=user.id, client=get_llm_client(), settings=get_settings()
    )
    return MessageOut.model_validate(message)


@router.patch("/messages/{message_id}/quiz-answers", response_model=MessageOut)
async def quiz_answers(
    message_id: uuid.UUID, data: QuizAnswersIn, session: SessionDep, user: CurrentUser
) -> MessageOut:
    """Save the student's picks for a quiz: one per question, null if not answered yet.

    The app grades them in code (the correct index is in the quiz); nothing about mastery or
    the plan changes. 422 if the message isn't a quiz or the count doesn't match."""
    message = await save_quiz_answers(session, message_id, data, user_id=user.id)
    return MessageOut.model_validate(message)


async def _prepared(
    conversation_id: uuid.UUID, data: MessageCreate, session: SessionDep, user: CurrentUser
) -> PreparedTurn:
    """Runs before the stream opens, so a conversation that isn't yours is a plain 404."""
    embedder = await asyncio.to_thread(get_embedder)  # loads the model on first use
    return await prepare_message(
        session, conversation_id, data, user_id=user.id, embedder=embedder, settings=get_settings()
    )


@router.post("/conversations/{conversation_id}/messages", response_class=EventSourceResponse)
async def ask(
    prepared: Annotated[PreparedTurn, Depends(_prepared)], session: SessionDep
) -> AsyncIterable[SourcesEvent | DeltaEvent | DoneEvent | ErrorEvent]:
    """Ask a question; the answer streams as server-sent events, in this order:

    - `sources`: the sources the answer is given (label, material, page), before any text;
    - `delta`: a piece of the answer's text (many);
    - `done` (the answer ended: message id, status, model, time to first token, cited
      labels) or `error` (a readable message, and when to retry if the AI is busy).

    The question is stored at once, the answer when it ends. If the client disconnects,
    the provider's stream is stopped and the partial answer is stored as `stopped`.
    """
    async with aclosing(run_turn(session, prepared, client=get_llm_client())) as events:
        async for event in events:
            yield ServerSentEvent(event=EVENT_NAMES[type(event)], data=event)  # type: ignore[misc]
