"""Call budgets, request pacing, cut-off replies and the usage detail (ADR 0007)."""

import httpx
import pytest
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import CallBudget, LLMClient
from app.ai.errors import AICallLimitReached, AIInvalidOutput, AITruncated, AIUnavailable
from app.ai.messages import user
from app.ai.usage import DbUsageStore, SessionFactory
from app.core.config import Settings
from app.models import AIUsage, User
from tests.ai.conftest import NOW
from tests.fakes import FakeLLM, ok, overloaded, rate_limited

MESSAGES = [user("Topics?")]


class Names(BaseModel):
    names: list[str]


class Clock:
    """A fake monotonic clock that the fake sleep moves forward."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(round(seconds, 3))
        self.now += seconds


def client_with(
    settings: Settings,
    fake_llm: FakeLLM,
    usage_sessions: SessionFactory,
    clock: Clock,
    **changes: object,
) -> LLMClient:
    return LLMClient(
        settings.model_copy(update=changes),
        DbUsageStore(usage_sessions),
        transport=fake_llm.transport,
        sleep=clock.sleep,
        now=lambda: NOW,
        jitter=lambda: 0.0,
        clock=clock,
    )


async def outcomes(session: AsyncSession, user_id: object) -> list[tuple[str, str | None]]:
    rows = await session.execute(
        select(AIUsage.outcome, AIUsage.detail).where(AIUsage.user_id == user_id)
    )
    return sorted((outcome, detail) for outcome, detail in rows)


# --- pacing ---


async def test_requests_wait_their_turn_within_the_per_minute_limit(
    settings: Settings, fake_llm: FakeLLM, usage_sessions: SessionFactory, user_a: User
) -> None:
    clock = Clock()
    client = client_with(
        settings, fake_llm, usage_sessions, clock, ai_requests_per_minute={"gemini/flash": 2}
    )
    fake_llm.reply("flash", ok("1"), ok("2"), ok("3"))

    for _ in range(3):
        await client.complete_text("smart", MESSAGES, purpose="t", user_id=user_a.id)

    assert clock.slept == [60.0]  # the third waited for the first to leave the window
    assert [sent.model for sent in fake_llm.requests] == ["flash"] * 3


async def test_no_limit_means_no_waiting(
    settings: Settings, fake_llm: FakeLLM, usage_sessions: SessionFactory, user_a: User
) -> None:
    clock = Clock()
    client = client_with(
        settings, fake_llm, usage_sessions, clock, ai_requests_per_minute={}, ai_daily_budget={}
    )
    fake_llm.reply("flash", *(ok(str(n)) for n in range(5)))

    for _ in range(5):
        await client.complete_text("smart", MESSAGES, purpose="t", user_id=user_a.id)

    assert clock.slept == []


# --- call budget ---


async def test_the_budget_counts_every_call_including_fallbacks(
    settings: Settings,
    fake_llm: FakeLLM,
    usage_sessions: SessionFactory,
    session: AsyncSession,
    user_a: User,
) -> None:
    client = client_with(settings, fake_llm, usage_sessions, Clock(), ai_retries=0)
    too_large = httpx.Response(413, json={"error": {"message": "Request too large"}})
    fake_llm.reply("flash", too_large)
    fake_llm.reply("oss-120b", too_large)
    budget = CallBudget(limit=1)

    with pytest.raises(AICallLimitReached) as raised:
        await client.complete_json(
            "smart", MESSAGES, Names, purpose="t", user_id=user_a.id, budget=budget
        )

    assert [sent.model for sent in fake_llm.requests] == ["flash"]  # Groq would be call 2
    assert budget.used == 1 and not raised.value.busy


async def test_turned_away_requests_have_their_own_wider_limit(
    settings: Settings, fake_llm: FakeLLM, usage_sessions: SessionFactory, user_a: User
) -> None:
    """429s and 503s ran nothing, so they don't use the call cap; their own cap ends a run."""
    client = client_with(settings, fake_llm, usage_sessions, Clock(), ai_retries=0)
    fake_llm.reply("flash", rate_limited(3600))
    fake_llm.reply("oss-120b", overloaded())
    budget = CallBudget(limit=1, turned_away_limit=2)

    with pytest.raises(AIUnavailable):
        await client.complete_json(
            "smart", MESSAGES, Names, purpose="t", user_id=user_a.id, budget=budget
        )
    assert (budget.used, budget.turned_away) == (0, 2)
    client._cooldown.clear()  # as if the job ran again after the cooldowns

    with pytest.raises(AICallLimitReached) as raised:
        await client.complete_json(
            "smart", MESSAGES, Names, purpose="t", user_id=user_a.id, budget=budget
        )
    assert raised.value.busy
    assert len(fake_llm.requests) == 2


async def test_no_repair_once_the_budget_has_used_its_repair(
    settings: Settings, fake_llm: FakeLLM, usage_sessions: SessionFactory, user_a: User
) -> None:
    client = client_with(settings, fake_llm, usage_sessions, Clock())
    fake_llm.reply("flash", ok('{"names": "not a list"}'))

    with pytest.raises(AIInvalidOutput):
        await client.complete_json(
            "smart",
            MESSAGES,
            Names,
            purpose="t",
            user_id=user_a.id,
            budget=CallBudget(limit=4, repairs_used=1),
        )

    assert len(fake_llm.requests) == 1


async def test_invalid_output_never_moves_to_another_model(
    settings: Settings, fake_llm: FakeLLM, usage_sessions: SessionFactory, user_a: User
) -> None:
    client = client_with(settings, fake_llm, usage_sessions, Clock())
    fake_llm.reply("flash", ok("nope"), ok("still nope"))

    with pytest.raises(AIInvalidOutput):
        await client.complete_json("smart", MESSAGES, Names, purpose="t", user_id=user_a.id)

    assert [sent.model for sent in fake_llm.requests] == ["flash", "flash"]  # one repair, no Groq


# --- cut-off replies and the usage detail ---


async def test_a_cut_off_reply_is_not_repaired(
    settings: Settings,
    fake_llm: FakeLLM,
    usage_sessions: SessionFactory,
    session: AsyncSession,
    user_a: User,
) -> None:
    client = client_with(settings, fake_llm, usage_sessions, Clock())
    fake_llm.reply("flash", ok('{"names": ["a", "b', finish_reason="length"))

    with pytest.raises(AITruncated):
        await client.complete_json("smart", MESSAGES, Names, purpose="t", user_id=user_a.id)

    assert len(fake_llm.requests) == 1
    assert await outcomes(session, user_a.id) == [("truncated", "finish_reason length")]


async def test_why_a_reply_was_invalid_is_recorded_without_its_text(
    settings: Settings,
    fake_llm: FakeLLM,
    usage_sessions: SessionFactory,
    session: AsyncSession,
    user_a: User,
) -> None:
    client = client_with(settings, fake_llm, usage_sessions, Clock())
    fake_llm.reply("flash", ok('{"names": "SECRET-REPLY-TEXT"}'), ok('{"names": ["ok"]}'))

    await client.complete_json("smart", MESSAGES, Names, purpose="t", user_id=user_a.id)

    rows = await outcomes(session, user_a.id)
    assert rows[0][0] == "invalid_json"
    assert rows[0][1] is not None and "names" in rows[0][1]
    assert all("SECRET-REPLY-TEXT" not in (detail or "") for _, detail in rows)
    assert rows[1] == ("ok", None)
