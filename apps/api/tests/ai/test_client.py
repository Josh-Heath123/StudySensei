"""The LLM client against a fake transport: success, backoff, fallback, budgets, JSON repair."""

import logging
from datetime import timedelta

import pytest
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.budget import next_reset, quota_zone, window_start
from app.ai.client import DEFAULT_COOLDOWN, LLMClient
from app.ai.errors import NOT_CONFIGURED, AIInvalidOutput, AIUnavailable
from app.ai.messages import Image, system, user
from app.ai.usage import DbUsageStore, SessionFactory
from app.core.config import Settings
from app.models import AIUsage, User
from tests.ai.conftest import GEMINI_KEY, GROQ_KEY, NOW, MakeClient, Sleeps, routes
from tests.fakes import FakeLLM, ok, rate_limited, server_error, unauthorized

MESSAGES = [system("You are a tutor."), user("What is a microservice?")]


async def usage(session: AsyncSession, user_id: object) -> list[tuple[str, str, str, int, int]]:
    rows = await session.execute(
        select(
            AIUsage.provider,
            AIUsage.model,
            AIUsage.outcome,
            AIUsage.input_tokens,
            AIUsage.output_tokens,
        )
        .where(AIUsage.user_id == user_id)
        .order_by(AIUsage.created_at, AIUsage.id)
    )
    return [tuple(row) for row in rows]  # type: ignore[misc]


async def outcomes(session: AsyncSession, user_id: object) -> list[tuple[str, str]]:
    # Rows written in one transaction share created_at; compare as a multiset by sorting.
    return sorted((f"{p}/{m}", o) for p, m, o, *_ in await usage(session, user_id))


async def spend(
    session: AsyncSession, user_a: User, key: str, count: int, *, hours_ago: float = 0
) -> None:
    """``count`` earlier requests to ``key`` (provider/model), as if made ``hours_ago``."""
    provider, _, model = key.partition("/")
    at = NOW - timedelta(hours=hours_ago)
    session.add_all(
        AIUsage(
            user_id=user_a.id,
            provider=provider,
            model=model,
            role="smart",
            purpose="earlier",
            latency_ms=100,
            outcome="ok",
            created_at=at,
        )
        for _ in range(count)
    )
    await session.commit()


# --- success ---


async def test_success_returns_the_text_and_logs_usage(
    make_client: MakeClient, fake_llm: FakeLLM, session: AsyncSession, user_a: User
) -> None:
    fake_llm.reply("flash", ok("A small service.", input_tokens=30, output_tokens=4))

    text = await make_client().complete_text("smart", MESSAGES, purpose="tutor", user_id=user_a.id)

    assert text == "A small service."
    [sent] = fake_llm.requests
    assert sent.host == "generativelanguage.googleapis.com"
    assert sent.body["messages"] == [
        {"role": "system", "content": "You are a tutor."},
        {"role": "user", "content": "What is a microservice?"},
    ]
    assert sent.headers["authorization"] == f"Bearer {GEMINI_KEY}"
    assert await usage(session, user_a.id) == [("gemini", "flash", "ok", 30, 4)]
    row = await session.scalar(select(AIUsage).where(AIUsage.user_id == user_a.id))
    assert row is not None and (row.role, row.purpose) == ("smart", "tutor")


async def test_bulk_role_uses_its_own_models(
    make_client: MakeClient, fake_llm: FakeLLM, user_a: User
) -> None:
    fake_llm.reply("flash-lite", ok("slides"))

    assert await make_client().complete_text("bulk", MESSAGES, purpose="tag", user_id=user_a.id)
    assert [sent.model for sent in fake_llm.requests] == ["flash-lite"]


async def test_no_user_details_reach_the_provider(
    make_client: MakeClient, fake_llm: FakeLLM, user_a: User
) -> None:
    fake_llm.reply("flash", ok("ok"))

    await make_client().complete_text("smart", MESSAGES, purpose="tutor", user_id=user_a.id)

    sent = fake_llm.sent_text() + str(fake_llm.requests[0].headers)
    assert user_a.email not in sent
    assert str(user_a.id) not in sent
    assert user_a.display_name is not None and user_a.display_name not in sent


async def test_an_image_goes_to_the_vision_role_whatever_role_was_asked(
    make_client: MakeClient, fake_llm: FakeLLM, session: AsyncSession, user_a: User
) -> None:
    # Gemini flash is the only vision model; with it rate-limited, no fallback can read images.
    page = Image(b"\x89PNG fake", "image/png")
    fake_llm.reply("flash", ok("Page text"))

    text = await make_client().complete_text(
        "bulk", [user("Transcribe this page.", page)], purpose="scan", user_id=user_a.id
    )

    assert text == "Page text"
    role = await session.scalar(select(AIUsage.role).where(AIUsage.user_id == user_a.id))
    assert role == "vision"
    content = fake_llm.requests[0].body["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "Transcribe this page."}
    assert content[1] == {"type": "image_url", "image_url": {"url": page.data_url()}}
    assert page.data_url().startswith("data:image/png;base64,")

    fake_llm.reply("flash", rate_limited(3600))
    with pytest.raises(AIUnavailable):
        await make_client().complete_text(
            "smart", [user("Again.", page)], purpose="scan", user_id=user_a.id
        )
    assert [sent.model for sent in fake_llm.requests] == ["flash", "flash"]  # never oss-120b


async def test_vision_falls_back_along_its_own_routes(
    make_client: MakeClient, fake_llm: FakeLLM, user_a: User
) -> None:
    client = make_client(ai_vision=routes("gemini/flash-lite", "groq/qwen-vl"))
    fake_llm.reply("flash-lite", rate_limited(3600))
    fake_llm.reply("qwen-vl", ok("From Qwen"))
    page = Image(b"page")

    text = await client.complete_text(
        "smart", [user("Read it.", page)], purpose="scan", user_id=user_a.id
    )

    assert text == "From Qwen"
    assert [sent.model for sent in fake_llm.requests] == ["flash-lite", "qwen-vl"]


async def test_text_requests_never_use_the_vision_role(
    make_client: MakeClient, fake_llm: FakeLLM, user_a: User
) -> None:
    client = make_client(ai_vision=routes("groq/qwen-vl"))
    fake_llm.reply("flash", ok("text"))

    await client.complete_text("smart", MESSAGES, purpose="tutor", user_id=user_a.id)

    assert [sent.model for sent in fake_llm.requests] == ["flash"]


async def test_no_vision_key_says_so_plainly(
    make_client: MakeClient, fake_llm: FakeLLM, user_a: User
) -> None:
    # Groq is set up for text, but the only vision model is on Gemini, which has no key.
    client = make_client(gemini_api_key=None)

    with pytest.raises(AIUnavailable) as caught:
        await client.complete_text(
            "smart", [user("Read it.", Image(b"page"))], purpose="scan", user_id=user_a.id
        )

    assert caught.value.retry_at is None
    assert "No configured model can read images" in str(caught.value)
    assert fake_llm.requests == []


# --- 429, 5xx and fallback ---


async def test_429_waits_for_retry_after_then_succeeds(
    make_client: MakeClient, fake_llm: FakeLLM, sleeps: Sleeps, session: AsyncSession, user_a: User
) -> None:
    fake_llm.reply("flash", rate_limited(retry_after=7), ok("Done"))

    text = await make_client().complete_text("smart", MESSAGES, purpose="tutor", user_id=user_a.id)

    assert text == "Done"
    assert sleeps.seconds == [7.0]  # jitter is 0 in tests
    assert await outcomes(session, user_a.id) == [
        ("gemini/flash", "ok"),
        ("gemini/flash", "rate_limited"),
    ]


async def test_jitter_is_added_to_the_wait(
    settings: Settings,
    fake_llm: FakeLLM,
    sleeps: Sleeps,
    usage_sessions: SessionFactory,
    user_a: User,
) -> None:
    fake_llm.reply("flash", rate_limited(retry_after=4), ok("Done"))
    client = LLMClient(
        settings,
        DbUsageStore(usage_sessions),
        transport=fake_llm.transport,
        sleep=sleeps,
        jitter=lambda: 0.5,
    )

    await client.complete_text("smart", MESSAGES, purpose="tutor", user_id=user_a.id)

    assert sleeps.seconds == [4.0 + 0.5 * 2.0]


async def test_429_without_retry_after_backs_off(
    make_client: MakeClient, fake_llm: FakeLLM, sleeps: Sleeps, user_a: User
) -> None:
    fake_llm.reply("flash", rate_limited(), ok("Done"))

    await make_client().complete_text("smart", MESSAGES, purpose="tutor", user_id=user_a.id)

    assert sleeps.seconds == [2.0]


async def test_a_long_retry_after_falls_through_to_the_next_provider(
    make_client: MakeClient, fake_llm: FakeLLM, sleeps: Sleeps, session: AsyncSession, user_a: User
) -> None:
    fake_llm.reply("flash", rate_limited(retry_after=3600))
    fake_llm.reply("oss-120b", ok("From Groq"))
    client = make_client()

    text = await client.complete_text("smart", MESSAGES, purpose="tutor", user_id=user_a.id)

    assert text == "From Groq"
    assert sleeps.seconds == []  # an hour isn't worth waiting for
    assert fake_llm.requests[1].host == "api.groq.com"
    assert fake_llm.requests[1].headers["authorization"] == f"Bearer {GROQ_KEY}"
    assert await outcomes(session, user_a.id) == [
        ("gemini/flash", "rate_limited"),
        ("groq/oss-120b", "ok"),
    ]

    # The same client remembers the cooldown and goes straight to Groq.
    fake_llm.reply("oss-120b", ok("Again"))
    await client.complete_text("smart", MESSAGES, purpose="tutor", user_id=user_a.id)
    assert [sent.model for sent in fake_llm.requests] == ["flash", "oss-120b", "oss-120b"]


async def test_repeated_5xx_falls_through_after_one_retry(
    make_client: MakeClient, fake_llm: FakeLLM, sleeps: Sleeps, session: AsyncSession, user_a: User
) -> None:
    fake_llm.reply("flash", server_error(), server_error())
    fake_llm.reply("oss-120b", ok("From Groq"))

    text = await make_client().complete_text("smart", MESSAGES, purpose="tutor", user_id=user_a.id)

    assert text == "From Groq"
    assert sleeps.seconds == [2.0]
    assert await outcomes(session, user_a.id) == [
        ("gemini/flash", "error"),
        ("gemini/flash", "error"),
        ("groq/oss-120b", "ok"),
    ]


async def test_a_bad_key_falls_through_without_waiting(
    make_client: MakeClient, fake_llm: FakeLLM, sleeps: Sleeps, user_a: User
) -> None:
    fake_llm.reply("flash", unauthorized())
    fake_llm.reply("oss-120b", ok("From Groq"))

    assert await make_client().complete_text(
        "smart", MESSAGES, purpose="tutor", user_id=user_a.id
    ) == ("From Groq")
    assert sleeps.seconds == []


async def test_every_provider_out_raises_ai_unavailable_with_the_earliest_retry(
    make_client: MakeClient, fake_llm: FakeLLM, session: AsyncSession, user_a: User
) -> None:
    fake_llm.reply("flash", rate_limited(retry_after=3600))
    fake_llm.reply("oss-120b", rate_limited(retry_after=600))

    with pytest.raises(AIUnavailable) as caught:
        await make_client().complete_text("smart", MESSAGES, purpose="tutor", user_id=user_a.id)

    assert caught.value.retry_at == NOW + timedelta(seconds=600)
    assert "Trying again after" in str(caught.value)


async def test_short_cooldowns_are_at_least_a_minute(
    make_client: MakeClient, fake_llm: FakeLLM, user_a: User
) -> None:
    fake_llm.reply("flash", server_error(), server_error())
    fake_llm.reply("oss-120b", server_error(), server_error())

    with pytest.raises(AIUnavailable) as caught:
        await make_client().complete_text("smart", MESSAGES, purpose="tutor", user_id=user_a.id)

    assert caught.value.retry_at == NOW + DEFAULT_COOLDOWN


async def test_no_provider_configured_says_so(
    make_client: MakeClient, fake_llm: FakeLLM, user_a: User
) -> None:
    client = make_client(gemini_api_key=None, groq_api_key=None)

    with pytest.raises(AIUnavailable) as caught:
        await client.complete_text("smart", MESSAGES, purpose="tutor", user_id=user_a.id)

    assert caught.value.retry_at is None
    assert str(caught.value) == NOT_CONFIGURED
    assert fake_llm.requests == []


async def test_a_provider_without_a_key_is_skipped(
    make_client: MakeClient, fake_llm: FakeLLM, user_a: User
) -> None:
    fake_llm.reply("oss-120b", ok("Groq only"))

    text = await make_client(gemini_api_key=None).complete_text(
        "smart", MESSAGES, purpose="tutor", user_id=user_a.id
    )

    assert text == "Groq only"
    assert [sent.model for sent in fake_llm.requests] == ["oss-120b"]


async def test_ollama_is_tried_last_without_a_key(
    make_client: MakeClient, fake_llm: FakeLLM, user_a: User
) -> None:
    fake_llm.reply("llama3.2", ok("Local"))

    text = await make_client(
        gemini_api_key=None, groq_api_key=None, ollama_model="llama3.2"
    ).complete_text("smart", MESSAGES, purpose="tutor", user_id=user_a.id)

    assert text == "Local"
    [sent] = fake_llm.requests
    assert sent.host == "localhost"
    assert "authorization" not in sent.headers


# --- daily budgets ---


async def test_a_used_up_budget_skips_the_model(
    make_client: MakeClient, fake_llm: FakeLLM, session: AsyncSession, user_a: User
) -> None:
    await spend(session, user_a, "gemini/flash", 3)  # its whole budget, today
    fake_llm.reply("oss-120b", ok("From Groq"))

    text = await make_client().complete_text("smart", MESSAGES, purpose="tutor", user_id=user_a.id)

    assert text == "From Groq"
    assert [sent.model for sent in fake_llm.requests] == ["oss-120b"]


async def test_every_budget_used_up_waits_for_the_first_reset(
    make_client: MakeClient,
    fake_llm: FakeLLM,
    settings: Settings,
    session: AsyncSession,
    user_a: User,
) -> None:
    await spend(session, user_a, "gemini/flash", 3)
    await spend(session, user_a, "groq/oss-120b", 5)

    with pytest.raises(AIUnavailable) as caught:
        await make_client().complete_text("smart", MESSAGES, purpose="tutor", user_id=user_a.id)

    resets = [next_reset(NOW, quota_zone(p, settings)) for p in ("gemini", "groq")]
    assert caught.value.retry_at == min(resets)
    assert fake_llm.requests == []


async def test_requests_before_the_quota_reset_dont_count(
    make_client: MakeClient,
    fake_llm: FakeLLM,
    settings: Settings,
    session: AsyncSession,
    user_a: User,
) -> None:
    start = window_start(NOW, quota_zone("gemini", settings))
    hours_since_reset = (NOW - start).total_seconds() / 3600
    await spend(session, user_a, "gemini/flash", 3, hours_ago=hours_since_reset + 0.1)
    fake_llm.reply("flash", ok("Fresh day"))

    assert await make_client().complete_text(
        "smart", MESSAGES, purpose="tutor", user_id=user_a.id
    ) == ("Fresh day")


async def test_rate_limited_requests_dont_use_the_budget(
    make_client: MakeClient, fake_llm: FakeLLM, session: AsyncSession, user_a: User
) -> None:
    session.add_all(
        AIUsage(
            user_id=user_a.id,
            provider="gemini",
            model="flash",
            role="smart",
            purpose="earlier",
            latency_ms=10,
            outcome="rate_limited",
        )
        for _ in range(5)
    )
    await session.commit()
    fake_llm.reply("flash", ok("Still allowed"))

    assert await make_client().complete_text(
        "smart", MESSAGES, purpose="tutor", user_id=user_a.id
    ) == ("Still allowed")


async def test_another_users_usage_doesnt_count(
    make_client: MakeClient,
    fake_llm: FakeLLM,
    session: AsyncSession,
    user_a: User,
    user_b: User,
) -> None:
    await spend(session, user_b, "gemini/flash", 3)
    fake_llm.reply("flash", ok("Mine"))

    assert await make_client().complete_text(
        "smart", MESSAGES, purpose="tutor", user_id=user_a.id
    ) == ("Mine")


# --- JSON ---


class TopicList(BaseModel):
    topics: list[str]


async def test_complete_json_validates_the_reply(
    make_client: MakeClient, fake_llm: FakeLLM, session: AsyncSession, user_a: User
) -> None:
    fake_llm.reply("flash", ok('```json\n{"topics": ["REST", "gRPC"]}\n```'))

    result = await make_client().complete_json(
        "smart", MESSAGES, TopicList, purpose="topics", user_id=user_a.id
    )

    assert result == TopicList(topics=["REST", "gRPC"])
    [sent] = fake_llm.requests
    assert sent.body["response_format"] == {"type": "json_object"}
    assert '"topics"' in sent.body["messages"][0]["content"]  # the schema is in the prompt


async def test_invalid_json_is_repaired_once(
    make_client: MakeClient, fake_llm: FakeLLM, session: AsyncSession, user_a: User
) -> None:
    fake_llm.reply("flash", ok('{"topics": "REST"}'), ok('{"topics": ["REST"]}'))

    result = await make_client().complete_json(
        "smart", MESSAGES, TopicList, purpose="topics", user_id=user_a.id
    )

    assert result.topics == ["REST"]
    repair = fake_llm.requests[1].body["messages"]
    assert repair[-2] == {"role": "assistant", "content": '{"topics": "REST"}'}
    assert "did not match the schema" in repair[-1]["content"]
    assert "topics" in repair[-1]["content"]
    assert await outcomes(session, user_a.id) == [
        ("gemini/flash", "invalid_json"),
        ("gemini/flash", "ok"),
    ]


async def test_invalid_json_twice_raises(
    make_client: MakeClient, fake_llm: FakeLLM, session: AsyncSession, user_a: User
) -> None:
    fake_llm.reply("flash", ok("not json"), ok("still not json"))

    with pytest.raises(AIInvalidOutput):
        await make_client().complete_json(
            "smart", MESSAGES, TopicList, purpose="topics", user_id=user_a.id
        )

    assert len(fake_llm.requests) == 2  # one repair, no fallback to another provider
    assert await outcomes(session, user_a.id) == [
        ("gemini/flash", "invalid_json"),
        ("gemini/flash", "invalid_json"),
    ]


# --- secrets ---


async def test_keys_never_reach_the_logs_or_usage(
    make_client: MakeClient,
    fake_llm: FakeLLM,
    session: AsyncSession,
    user_a: User,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    fake_llm.reply("flash", unauthorized())
    fake_llm.reply("oss-120b", rate_limited(3600))

    with pytest.raises(AIUnavailable) as caught:
        await make_client().complete_text("smart", MESSAGES, purpose="tutor", user_id=user_a.id)

    rows = str(await usage(session, user_a.id))
    for key in (GEMINI_KEY, GROQ_KEY):
        assert key not in caplog.text
        assert key not in str(caught.value)
        assert key not in rows
