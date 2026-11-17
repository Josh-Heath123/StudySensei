"""503 "high demand" and content refusals: both move on to the next model (ADR 0008)."""

from datetime import timedelta

import pytest
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import CallBudget
from app.ai.errors import AIRefused, AITruncated
from app.ai.usage import count_requests
from app.models import AIUsage, User
from tests.ai.conftest import NOW, MakeClient, Sleeps
from tests.ai.test_client import MESSAGES, outcomes
from tests.fakes import FakeLLM, ok, overloaded, refused


class Names(BaseModel):
    names: list[str]


async def details(session: AsyncSession, user_id: object) -> list[tuple[str, str | None]]:
    rows = await session.execute(
        select(AIUsage.outcome, AIUsage.detail).where(AIUsage.user_id == user_id)
    )
    return sorted((outcome, detail) for outcome, detail in rows)


# --- 503 "high demand" ---


async def test_a_busy_model_is_retried_then_the_next_one_answers(
    make_client: MakeClient, fake_llm: FakeLLM, sleeps: Sleeps, session: AsyncSession, user_a: User
) -> None:
    fake_llm.reply("flash", overloaded(), overloaded())
    fake_llm.reply("oss-120b", ok("From Groq"))

    text = await make_client().complete_text("smart", MESSAGES, purpose="tutor", user_id=user_a.id)

    assert text == "From Groq"
    assert sleeps.seconds == [2.0]  # one short retry on the busy model first
    assert await outcomes(session, user_a.id) == [
        ("gemini/flash", "overloaded"),
        ("gemini/flash", "overloaded"),
        ("groq/oss-120b", "ok"),
    ]


async def test_busy_replies_use_neither_the_daily_budget_nor_the_call_cap(
    make_client: MakeClient, fake_llm: FakeLLM, session: AsyncSession, user_a: User
) -> None:
    fake_llm.reply("flash", overloaded(), overloaded())
    fake_llm.reply("oss-120b", ok('{"names": ["a"]}'))
    budget = CallBudget(limit=4, turned_away_limit=20)

    await make_client().complete_json(
        "smart", MESSAGES, Names, purpose="t", user_id=user_a.id, budget=budget
    )

    assert (budget.used, budget.turned_away) == (1, 2)
    since = NOW - timedelta(days=1)
    assert (
        await count_requests(
            session, user_id=user_a.id, provider="gemini", model="flash", since=since
        )
        == 0
    )
    detail = await session.scalar(
        select(AIUsage.detail).where(AIUsage.user_id == user_a.id, AIUsage.outcome == "overloaded")
    )
    assert detail is not None and "HTTP 503" in detail and "high demand" in detail


# --- content refusals ---


@pytest.mark.parametrize("finish_reason", ["content_filter", "SAFETY", "PROHIBITED_CONTENT"])
async def test_a_filtered_reply_moves_on_without_using_the_repair(
    finish_reason: str,
    make_client: MakeClient,
    fake_llm: FakeLLM,
    sleeps: Sleeps,
    session: AsyncSession,
    user_a: User,
) -> None:
    fake_llm.reply("flash", refused(finish_reason))
    fake_llm.reply("oss-120b", ok('{"names": ["Firewalls"]}'))
    budget = CallBudget(limit=4)

    result = await make_client().complete_json(
        "smart", MESSAGES, Names, purpose="t", user_id=user_a.id, budget=budget
    )

    assert result.names == ["Firewalls"]
    assert (budget.used, budget.repairs_used) == (2, 0)
    assert sleeps.seconds == []  # no waiting: the next model just gets it
    assert await details(session, user_a.id) == [
        ("ok", None),
        ("refused", f"finish_reason {finish_reason}"),
    ]


async def test_an_empty_reply_counts_as_a_refusal(
    make_client: MakeClient, fake_llm: FakeLLM, session: AsyncSession, user_a: User
) -> None:
    fake_llm.reply("flash", ok("   ", finish_reason="stop"))
    fake_llm.reply("oss-120b", ok('{"names": []}'))
    budget = CallBudget(limit=4)

    await make_client().complete_json(
        "smart", MESSAGES, Names, purpose="t", user_id=user_a.id, budget=budget
    )

    assert budget.repairs_used == 0
    assert ("refused", "empty reply") in await details(session, user_a.id)


async def test_a_refusal_doesnt_cool_the_model_down(
    make_client: MakeClient, fake_llm: FakeLLM, user_a: User
) -> None:
    """It's this content the model won't answer, not the model that's unavailable."""
    client = make_client()
    fake_llm.reply("flash", refused(), ok("Second request"))
    fake_llm.reply("oss-120b", ok("From Groq"))

    assert await client.complete_text("smart", MESSAGES, purpose="t", user_id=user_a.id) == (
        "From Groq"
    )
    assert await client.complete_text("smart", MESSAGES, purpose="t", user_id=user_a.id) == (
        "Second request"
    )


async def test_every_model_refusing_fails_plainly(
    make_client: MakeClient, fake_llm: FakeLLM, session: AsyncSession, user_a: User
) -> None:
    fake_llm.reply("flash", refused("SAFETY"))
    fake_llm.reply("oss-120b", refused())

    with pytest.raises(AIRefused) as caught:
        await make_client().complete_text("smart", MESSAGES, purpose="t", user_id=user_a.id)

    message = str(caught.value)
    assert "declined" in message
    assert "gemini/flash: finish_reason SAFETY" in message
    assert "groq/oss-120b: finish_reason content_filter" in message
    # Refusals ran (and were filtered), so they count toward the daily budget.
    assert sorted(o for _, o in await outcomes(session, user_a.id)) == ["refused", "refused"]


async def test_a_cut_off_reply_is_not_a_refusal(
    make_client: MakeClient, fake_llm: FakeLLM, user_a: User
) -> None:
    fake_llm.reply("flash", ok("", finish_reason="length"))

    with pytest.raises(AITruncated):
        await make_client().complete_text("smart", MESSAGES, purpose="t", user_id=user_a.id)
