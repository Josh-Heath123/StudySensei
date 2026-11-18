"""POST /ai/ping: every configured model at once, on the fake transport only."""

from typing import Any

import httpx
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LLMClient, set_llm_client
from app.ai.usage import DbUsageStore
from app.models import AIUsage, User
from tests.ai.conftest import shared_session
from tests.api.conftest import PING_GEMINI_KEY, PING_GROQ_KEY, ping_settings
from tests.fakes import FakeLLM, ok, unauthorized


def result(body: dict[str, Any], model: str) -> dict[str, Any]:
    return next(r for r in body["results"] if r["model"] == model)


def all_answer(fake: FakeLLM) -> None:
    for model in ("flash", "flash-lite", "oss-120b"):
        fake.reply(model, ok("pong"))


async def test_every_configured_model_answers_once(
    ping_llm: FakeLLM, alice_api: AsyncClient, session: AsyncSession, user_a: User
) -> None:
    all_answer(ping_llm)

    response = await alice_api.post("/ai/ping")

    assert response.status_code == 200
    body = response.json()
    # Role order: smart (flash, oss-120b), then bulk's flash-lite.
    assert [(r["provider"], r["model"]) for r in body["results"]] == [
        ("gemini", "flash"),
        ("groq", "oss-120b"),
        ("gemini", "flash-lite"),
    ]
    flash = result(body, "flash")
    assert flash["status"] == "ok"
    assert isinstance(flash["latency_ms"], int)
    assert (flash["error"], flash["resets_at"]) == (None, None)
    assert (flash["in_models_list"], flash["models_list_error"]) == (True, None)
    assert sorted(sent.model for sent in ping_llm.requests) == ["flash", "flash-lite", "oss-120b"]
    rows = (await session.scalars(select(AIUsage).where(AIUsage.purpose == "ping"))).all()
    assert len(rows) == 3
    assert {(row.user_id, row.outcome) for row in rows} == {(user_a.id, "ok")}


async def test_a_failure_carries_the_providers_text_and_never_a_key(
    ping_llm: FakeLLM, alice_api: AsyncClient, session: AsyncSession
) -> None:
    ping_llm.reply("flash", ok("pong"))
    ping_llm.reply("flash-lite", ok("pong"))
    ping_llm.reply("oss-120b", unauthorized())

    response = await alice_api.post("/ai/ping")

    groq = result(response.json(), "oss-120b")
    assert groq["status"] == "failed"
    assert groq["error"] == "groq: HTTP 401: bad key"
    assert isinstance(groq["latency_ms"], int)
    assert result(response.json(), "flash")["status"] == "ok"
    assert PING_GROQ_KEY not in response.text and PING_GEMINI_KEY not in response.text
    outcomes = await session.scalars(
        select(AIUsage.outcome).where(AIUsage.purpose == "ping", AIUsage.model == "oss-120b")
    )
    assert list(outcomes) == ["error"]


async def test_a_lost_connection_is_a_failure_and_the_rest_still_run(
    ping_llm: FakeLLM, alice_api: AsyncClient
) -> None:
    ping_llm.reply("flash", httpx.ConnectError("refused"))
    ping_llm.reply("flash-lite", ok("pong"))
    ping_llm.reply("oss-120b", ok("pong"))

    body = (await alice_api.post("/ai/ping")).json()

    assert result(body, "flash")["status"] == "failed"
    assert result(body, "flash")["error"] == "gemini: couldn't connect (ConnectError)"
    assert result(body, "flash-lite")["status"] == "ok"


async def test_a_model_missing_from_models_is_flagged(
    ping_llm: FakeLLM, alice_api: AsyncClient
) -> None:
    all_answer(ping_llm)
    ping_llm.unlisted.add("flash-lite")

    body = (await alice_api.post("/ai/ping")).json()

    assert result(body, "flash-lite")["in_models_list"] is False
    assert result(body, "flash-lite")["status"] == "ok"
    assert result(body, "flash")["in_models_list"] is True


async def test_a_used_up_budget_is_skipped_not_called(
    ping_llm: FakeLLM, alice_api: AsyncClient, session: AsyncSession, user_a: User
) -> None:
    for _ in range(2):  # Flash's budget is two a day
        session.add(
            AIUsage(
                user_id=user_a.id,
                provider="gemini",
                model="flash",
                role="smart",
                purpose="tutor",
                latency_ms=500,
                outcome="ok",
            )
        )
    await session.commit()
    ping_llm.reply("flash-lite", ok("pong"))
    ping_llm.reply("oss-120b", ok("pong"))

    body = (await alice_api.post("/ai/ping")).json()

    flash = result(body, "flash")
    assert flash["status"] == "skipped"
    assert flash["resets_at"] is not None
    assert (flash["latency_ms"], flash["error"]) == (None, None)
    assert "flash" not in [sent.model for sent in ping_llm.requests]
    pings = await session.scalars(
        select(AIUsage).where(AIUsage.purpose == "ping", AIUsage.model == "flash")
    )
    assert list(pings) == []


async def test_with_no_providers_nothing_is_called(
    alice_api: AsyncClient, session: AsyncSession
) -> None:
    fake = FakeLLM()
    usage = DbUsageStore(shared_session(session))
    set_llm_client(LLMClient(ping_settings(keys=False), usage, transport=fake.transport))

    response = await alice_api.post("/ai/ping")

    assert response.status_code == 200
    assert response.json() == {"results": []}
    assert fake.requests == []
    assert list(await session.scalars(select(AIUsage))) == []
