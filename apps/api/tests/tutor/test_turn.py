"""A turn without HTTP: citations, history within the budget, and stopping part-way."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LLMClient
from app.core.config import get_settings
from app.models import AIUsage, Message
from app.schemas.tutor import ConversationCreate, DeltaEvent, MessageCreate, SourcesEvent
from app.services.tutor.citations import parse_citations
from app.services.tutor.conversations import (
    create_conversation,
    prepare_message,
    recent_exchanges,
    run_turn,
)
from app.services.tutor.prompts import (
    Exchange,
    estimate_tokens,
    fit_history,
    history_messages,
    history_tokens,
)
from app.services.tutor.turn import build_turn
from tests.fakes import FakeEmbedder, FakeLLM, StreamedBody, stream_events, streamed
from tests.tutor.conftest import Module

# --- citations ---


def test_citations_in_every_form_are_found_once_in_source_order() -> None:
    labels = ["S1", "S2", "S3"]

    found = parse_citations("A [S3]. B [S1][S3]. C [S2, S1]. D [ S2 ; S3 ].", labels)

    assert (found.cited, found.unknown) == (["S1", "S2", "S3"], [])


def test_full_width_brackets_count_too() -> None:
    """gpt-oss's own style, seen on COS330: 【S1】 and 【S1】【S4】."""
    found = parse_citations(
        "Reachable flaws【S1】. Ports【S1】【S4】 and [S2].", ["S1", "S2", "S4"]
    )

    assert (found.cited, found.unknown) == (["S1", "S2", "S4"], [])


def test_labels_that_werent_given_are_reported_apart() -> None:
    found = parse_citations("A [S1]. B [S9]. C [S4, S2]. D [S9].", ["S1", "S2", "S3"])

    assert (found.cited, found.unknown) == (["S1", "S2"], ["S9", "S4"])


def test_text_without_labels_cites_nothing() -> None:
    for text in ("The sources don't cover this.", "See S1 or [1] or [Source 1].", ""):
        assert parse_citations(text, ["S1"]) == parse_citations("", ["S1"])
        assert parse_citations(text, ["S1"]).cited == []


# --- history ---


def test_history_goes_in_as_chat_turns_without_labels() -> None:
    messages = history_messages([Exchange("What is a salt?", "Random data [S1]【S2, S3】.")])

    assert [(m.role, m.text) for m in messages] == [
        ("user", "Student's question: What is a salt?"),
        ("assistant", "Random data."),
    ]


def test_the_oldest_exchange_is_dropped_first_to_fit() -> None:
    old, middle, new = (Exchange(f"q{n}", "a" * 350) for n in range(3))
    each = history_tokens([new])

    assert fit_history([old, middle, new], 3 * each) == [old, middle, new]
    assert fit_history([old, middle, new], 2 * each) == [middle, new]
    assert fit_history([old, middle, new], each) == [new]
    assert fit_history([old, middle, new], each - 1) == []


async def test_the_sources_come_first_and_the_history_gets_what_is_left(
    session: AsyncSession, module: Module, fake_embedder: FakeEmbedder
) -> None:
    question = "How does a stateful inspection firewall work?"
    long_answer = "x " * 2000  # about 1,150 tokens each
    history = [Exchange("first", long_answer), Exchange("second", long_answer)]
    full = await build_turn(
        session,
        module.module_id,
        question,
        "answer",
        user_id=module.user_id,
        topic_id=None,
        history=history,
        embedder=fake_embedder,
        settings=get_settings(),
    )
    # A budget with room for the sources and only one exchange.
    tight = get_settings().model_copy(
        update={"tutor_context_max_tokens": full.context_tokens + history_tokens(history[1:])}
    )
    trimmed = await build_turn(
        session,
        module.module_id,
        question,
        "answer",
        user_id=module.user_id,
        topic_id=None,
        history=history,
        embedder=fake_embedder,
        settings=tight,
    )

    assert full.history_used == 2
    assert [s.chunk_id for s in trimmed.sources] == [s.chunk_id for s in full.sources]
    assert trimmed.history_used == 1
    assert trimmed.messages[1].text == "Student's question: second"  # the newest kept
    assert trimmed.context_tokens + trimmed.history_tokens <= tight.tutor_context_max_tokens
    # Every source block is whole.
    prompt = trimmed.messages[-1].text
    assert all(source.text.strip() in prompt for source in trimmed.sources)
    assert estimate_tokens(prompt) > 0


async def test_only_answered_exchanges_count_as_history(
    session: AsyncSession, module: Module
) -> None:
    conversation = await create_conversation(
        session, module.module_id, ConversationCreate(), user_id=module.user_id
    )
    turns = [
        ("q1", "a1", "complete"),
        ("q2", "", "failed"),
        ("q3", "a3 partial", "stopped"),
        ("q4", "a4 cut", "truncated"),
    ]
    position = 0
    for question, reply, status in turns:
        for role, text, state in (("user", question, "complete"), ("assistant", reply, status)):
            session.add(
                Message(
                    user_id=module.user_id,
                    conversation_id=conversation.id,
                    position=position,
                    role=role,
                    mode="answer",
                    text=text,
                    status=state,
                )
            )
            position += 1
    await session.commit()

    exchanges = await recent_exchanges(session, conversation.id, user_id=module.user_id)

    assert exchanges == [Exchange("q1", "a1"), Exchange("q4", "a4 cut")]


# --- stopping part-way ---


async def test_closing_the_turn_stops_the_provider_and_stores_what_was_said(
    session: AsyncSession,
    module: Module,
    fake_embedder: FakeEmbedder,
    tutor_llm: LLMClient,
    fake_llm: FakeLLM,
) -> None:
    body = StreamedBody(stream_events("It tracks ", "never sent"), pause_after=1)
    fake_llm.reply("flash", streamed(body=body))
    conversation = await create_conversation(
        session, module.module_id, ConversationCreate(), user_id=module.user_id
    )
    prepared = await prepare_message(
        session,
        conversation.id,
        MessageCreate(question="How does a stateful firewall work?"),
        user_id=module.user_id,
        embedder=fake_embedder,
        settings=get_settings(),
    )
    events = run_turn(session, prepared, client=tutor_llm)

    first = await anext(events)
    second = await anext(events)
    await events.aclose()

    assert isinstance(first, SourcesEvent) and second == DeltaEvent(text="It tracks ")
    assert body.closed
    reply = await session.scalar(
        select(Message).where(
            Message.conversation_id == conversation.id, Message.role == "assistant"
        )
    )
    assert reply is not None
    assert (reply.status, reply.text, reply.model) == ("stopped", "It tracks ", "gemini/flash")
    assert await session.scalar(select(AIUsage.outcome)) == "stopped"
