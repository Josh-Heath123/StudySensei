"""Streaming (ADR 0013): fallback only before the first token, the interactive rule, the end."""

import asyncio

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.adapter import sse_data
from app.ai.client import LLMClient, StreamDone, TextDelta
from app.ai.errors import AIRefused, AIRequestFailed, AIStreamFailed, AIUnavailable
from app.models import AIUsage, User
from tests.ai.conftest import MakeClient, Sleeps
from tests.ai.test_client import MESSAGES, outcomes, spend
from tests.fakes import (
    FakeLLM,
    StreamedBody,
    overloaded,
    rate_limited,
    server_error,
    stream_events,
    streamed,
    unauthorized,
)


async def collect(
    client: LLMClient, user: User, *, interactive: bool = True
) -> tuple[list[str], StreamDone]:
    pieces: list[str] = []
    done: StreamDone | None = None
    async for item in client.stream_text(
        "smart", MESSAGES, purpose="tutor", user_id=user.id, interactive=interactive
    ):
        if isinstance(item, TextDelta):
            pieces.append(item.text)
        else:
            done = item
    assert done is not None
    return pieces, done


def too_large() -> httpx.Response:
    return httpx.Response(413, json={"error": {"message": "Request too large: Limit 8000"}})


# --- the happy path ---


async def test_the_answer_streams_without_the_thinking_and_ends_with_usage(
    make_client: MakeClient, fake_llm: FakeLLM, session: AsyncSession, user_a: User
) -> None:
    fake_llm.reply(
        "flash",
        streamed(
            "A micro", "service is ", "small [S1].", reasoning=["Let me think"], output_tokens=9
        ),
    )

    pieces, done = await collect(make_client(), user_a)

    assert pieces == ["A micro", "service is ", "small [S1]."]
    assert (done.route.key, done.finish_reason, done.truncated) == ("gemini/flash", "stop", False)
    assert (done.input_tokens, done.output_tokens) == (12, 9)
    assert 0 <= done.first_token_ms <= done.total_ms
    sent = fake_llm.requests[0].body
    assert sent["stream"] is True and sent["stream_options"] == {"include_usage": True}
    rows = (
        await session.execute(
            select(AIUsage.outcome, AIUsage.purpose, AIUsage.output_tokens, AIUsage.detail).where(
                AIUsage.user_id == user_a.id
            )
        )
    ).all()
    assert [tuple(row) for row in rows] == [("ok", "tutor", 9, None)]
    # Never prompt or reply text in the usage row.
    assert "micro" not in str(rows)


async def test_sse_data_joins_lines_and_skips_comments() -> None:
    async def lines() -> object:
        for line in [": keep-alive", "event: message", "data: a", "data: b", "", "data: c"]:
            yield line

    assert [data async for data in sse_data(lines())] == ["a\nb", "c"]  # type: ignore[arg-type]


async def test_an_error_event_in_the_stream_is_a_provider_error(
    make_client: MakeClient, fake_llm: FakeLLM, session: AsyncSession, user_a: User
) -> None:
    body = StreamedBody([{"error": {"message": "overloaded", "code": 503}}])
    fake_llm.reply("flash", streamed(body=body))
    fake_llm.reply("oss-120b", streamed("From Groq"))

    pieces, done = await collect(make_client(), user_a)

    assert (pieces, done.route.key) == (["From Groq"], "groq/oss-120b")
    assert await outcomes(session, user_a.id) == [
        ("gemini/flash", "overloaded"),
        ("groq/oss-120b", "ok"),
    ]


# --- fallback before the first token, never after ---


@pytest.mark.parametrize(
    ("first", "outcome"),
    [
        (overloaded(), "overloaded"),
        (rate_limited(), "rate_limited"),
        (too_large(), "too_large"),
        (httpx.ReadTimeout("slow"), "timeout"),
        (httpx.ConnectError("refused"), "error"),
    ],
)
async def test_before_the_first_token_the_next_model_answers(
    make_client: MakeClient,
    fake_llm: FakeLLM,
    sleeps: Sleeps,
    session: AsyncSession,
    user_a: User,
    first: httpx.Response | Exception,
    outcome: str,
) -> None:
    fake_llm.reply("flash", first)
    fake_llm.reply("oss-120b", streamed("From ", "Groq"))

    pieces, done = await collect(make_client(), user_a)

    assert (pieces, done.route.key) == (["From ", "Groq"], "groq/oss-120b")
    assert sleeps.seconds == []  # interactive: no waiting
    assert await outcomes(session, user_a.id) == [
        ("gemini/flash", outcome),
        ("groq/oss-120b", "ok"),
    ]


async def test_a_connection_lost_before_any_answer_token_falls_back(
    make_client: MakeClient, fake_llm: FakeLLM, session: AsyncSession, user_a: User
) -> None:
    # Thinking arrived, then the connection dropped: nothing was shown, so fall back.
    body = StreamedBody(stream_events("never", reasoning=["hmm"]), fail_after=0)
    fake_llm.reply("flash", streamed(body=body))
    fake_llm.reply("oss-120b", streamed("From Groq"))

    pieces, done = await collect(make_client(), user_a)

    assert (pieces, done.route.key) == (["From Groq"], "groq/oss-120b")


async def test_a_refusal_before_any_token_falls_back(
    make_client: MakeClient, fake_llm: FakeLLM, session: AsyncSession, user_a: User
) -> None:
    fake_llm.reply("flash", streamed(finish_reason="content_filter"))
    fake_llm.reply("oss-120b", streamed("From Groq"))

    pieces, done = await collect(make_client(), user_a)

    assert (pieces, done.route.key) == (["From Groq"], "groq/oss-120b")
    assert await outcomes(session, user_a.id) == [
        ("gemini/flash", "refused"),
        ("groq/oss-120b", "ok"),
    ]


async def test_when_every_model_refuses_it_says_so(
    make_client: MakeClient, fake_llm: FakeLLM, user_a: User
) -> None:
    fake_llm.reply("flash", streamed(finish_reason="safety"))
    fake_llm.reply("oss-120b", streamed())  # an empty reply

    with pytest.raises(AIRefused):
        await collect(make_client(), user_a)


async def test_after_the_first_token_a_lost_connection_ends_the_stream(
    make_client: MakeClient, fake_llm: FakeLLM, session: AsyncSession, user_a: User
) -> None:
    body = StreamedBody(stream_events("One ", "two ", "three"), fail_after=2)
    fake_llm.reply("flash", streamed(body=body))
    pieces: list[str] = []

    with pytest.raises(AIStreamFailed) as failed:
        async for item in make_client().stream_text(
            "smart", MESSAGES, purpose="tutor", user_id=user_a.id
        ):
            assert isinstance(item, TextDelta)
            pieces.append(item.text)

    assert pieces == ["One ", "two "]
    assert failed.value.model == "gemini/flash"
    # Groq was never asked: two models' text is never spliced.
    assert [r.model for r in fake_llm.requests] == ["flash"]
    assert await outcomes(session, user_a.id) == [("gemini/flash", "error")]


async def test_a_refusal_part_way_ends_the_stream(
    make_client: MakeClient, fake_llm: FakeLLM, user_a: User
) -> None:
    fake_llm.reply("flash", streamed("Partly ", finish_reason="content_filter"))

    with pytest.raises(AIStreamFailed, match="part-way"):
        await collect(make_client(), user_a)
    assert [r.model for r in fake_llm.requests] == ["flash"]


# --- the interactive rule (ADR 0013) against the background rule ---


async def test_interactive_moves_straight_on_from_a_busy_model(
    make_client: MakeClient, fake_llm: FakeLLM, sleeps: Sleeps, user_a: User
) -> None:
    fake_llm.reply("flash", overloaded())
    fake_llm.reply("oss-120b", streamed("Now"))

    _, done = await collect(make_client(), user_a, interactive=True)

    assert (done.route.key, sleeps.seconds) == ("groq/oss-120b", [])


async def test_a_background_stream_retries_the_busy_model_first(
    make_client: MakeClient, fake_llm: FakeLLM, sleeps: Sleeps, session: AsyncSession, user_a: User
) -> None:
    fake_llm.reply("flash", overloaded(), streamed("After a wait"))

    pieces, done = await collect(make_client(), user_a, interactive=False)

    assert (pieces, done.route.key) == (["After a wait"], "gemini/flash")
    assert sleeps.seconds == [2.0]
    assert await outcomes(session, user_a.id) == [
        ("gemini/flash", "ok"),
        ("gemini/flash", "overloaded"),
    ]


async def test_interactive_doesnt_wait_out_a_rate_limit_either(
    make_client: MakeClient, fake_llm: FakeLLM, sleeps: Sleeps, user_a: User
) -> None:
    fake_llm.reply("flash", rate_limited(retry_after=3))
    fake_llm.reply("oss-120b", streamed("Now"))

    _, done = await collect(make_client(), user_a)

    assert (done.route.key, sleeps.seconds) == ("groq/oss-120b", [])


async def test_a_bad_key_fails_visibly_and_isnt_passed_on(
    make_client: MakeClient, fake_llm: FakeLLM, user_a: User
) -> None:
    fake_llm.reply("flash", unauthorized())

    with pytest.raises(AIRequestFailed, match="HTTP 401"):
        await collect(make_client(), user_a)
    assert [r.model for r in fake_llm.requests] == ["flash"]


async def test_an_interactive_server_error_fails_at_once(
    make_client: MakeClient, fake_llm: FakeLLM, sleeps: Sleeps, user_a: User
) -> None:
    fake_llm.reply("flash", server_error())

    with pytest.raises(AIUnavailable) as unavailable:
        await collect(make_client(), user_a)
    assert sleeps.seconds == []
    assert unavailable.value.retry_at is not None


async def test_a_model_out_of_budget_is_skipped(
    make_client: MakeClient, fake_llm: FakeLLM, session: AsyncSession, user_a: User
) -> None:
    await spend(session, user_a, "gemini/flash", 3)
    fake_llm.reply("oss-120b", streamed("From Groq"))

    _, done = await collect(make_client(), user_a)

    assert done.route.key == "groq/oss-120b"


async def test_with_every_model_busy_it_says_when_to_retry(
    make_client: MakeClient, fake_llm: FakeLLM, user_a: User
) -> None:
    fake_llm.reply("flash", overloaded())
    fake_llm.reply("oss-120b", rate_limited(retry_after=30))

    with pytest.raises(AIUnavailable) as unavailable:
        await collect(make_client(), user_a)
    assert unavailable.value.retry_at is not None
    assert "Trying again after" in str(unavailable.value)


# --- the end of the stream ---


async def test_hitting_the_output_limit_ends_normally_marked_truncated(
    make_client: MakeClient, fake_llm: FakeLLM, session: AsyncSession, user_a: User
) -> None:
    fake_llm.reply("flash", streamed("A long ", "answer", finish_reason="length"))

    pieces, done = await collect(make_client(), user_a)

    assert pieces == ["A long ", "answer"]
    assert done.truncated
    assert await outcomes(session, user_a.id) == [("gemini/flash", "truncated")]


async def test_closing_the_stream_closes_the_providers_and_logs_it_stopped(
    make_client: MakeClient, fake_llm: FakeLLM, session: AsyncSession, user_a: User
) -> None:
    body = StreamedBody(stream_events("First ", "never sent"), pause_after=1)
    fake_llm.reply("flash", streamed(body=body))
    stream = make_client().stream_text("smart", MESSAGES, purpose="tutor", user_id=user_a.id)

    first = await anext(stream)
    await stream.aclose()

    assert first == TextDelta("First ", "gemini/flash")
    assert body.closed
    assert await outcomes(session, user_a.id) == [("gemini/flash", "stopped")]


async def test_cancelling_the_reader_stops_the_provider_stream(
    make_client: MakeClient, fake_llm: FakeLLM, session: AsyncSession, user_a: User
) -> None:
    body = StreamedBody(stream_events("First ", "never sent"), pause_after=1)
    fake_llm.reply("flash", streamed(body=body))
    seen: list[str] = []
    got_one = asyncio.Event()

    async def read() -> None:
        async for item in make_client().stream_text(
            "smart", MESSAGES, purpose="tutor", user_id=user_a.id
        ):
            if isinstance(item, TextDelta):
                seen.append(item.text)
                got_one.set()

    task = asyncio.create_task(read())
    await got_one.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert seen == ["First "]
    assert body.closed
    assert await outcomes(session, user_a.id) == [("gemini/flash", "stopped")]
