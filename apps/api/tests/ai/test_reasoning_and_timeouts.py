"""reasoning_effort per route and per call, timeouts, and the ping's own time limit."""

import io

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.messages import user
from app.ai.ping import run_pings
from app.ai.routes import all_routes, routes_for, wire_effort
from app.core.config import RouteSetting, Settings, get_settings
from app.models import AIUsage, User
from tests.ai.conftest import MakeClient, Sleeps, routes
from tests.fakes import FakeLLM, ok

MESSAGES = [user("Hello")]
GEMINI_FLASH = "gemini-3.8-flash"
GEMINI_LITE = "gemini-3.5-flash-lite"
GPT_OSS = "openai/gpt-oss-120b"
QWEN = "qwen/qwen3.8-27b"


def sent_effort(fake_llm: FakeLLM) -> list[str | None]:
    return [sent.body.get("reasoning_effort") for sent in fake_llm.requests]


# --- what is sent where ---


@pytest.mark.parametrize(
    ("provider", "model", "effort", "sent"),
    [
        ("gemini", GEMINI_FLASH, "low", "low"),
        ("gemini", GEMINI_LITE, "minimal", "minimal"),
        ("gemini", GEMINI_FLASH, None, None),
        ("groq", GPT_OSS, "medium", "medium"),
        ("groq", "openai/gpt-oss-20b", "minimal", "low"),  # gpt-oss has no "minimal"
        ("groq", QWEN, "low", None),  # Qwen takes other values: not sent
        ("ollama", "llama3.2", "low", None),
    ],
)
def test_wire_effort(provider: str, model: str, effort: str | None, sent: str | None) -> None:
    assert wire_effort(provider, model, effort) == sent  # type: ignore[arg-type]


def test_default_roles_think_minimal_for_bulk_and_low_for_smart() -> None:
    defaults = get_settings()

    assert {r.key: r.reasoning_effort for r in routes_for("bulk", defaults)} == {
        f"gemini/{GEMINI_LITE}": "minimal",
        "groq/openai/gpt-oss-20b": "minimal",
    }
    assert {r.reasoning_effort for r in routes_for("smart", defaults)} == {"low"}


def test_env_accepts_plain_strings_and_blank_effort() -> None:
    parsed = Settings(
        ai_smart=["gemini/x", {"route": "groq/y", "reasoning_effort": ""}],
        ai_bulk=[{"route": "gemini/z", "reasoning_effort": "high"}],
    )

    assert parsed.ai_smart == [RouteSetting(route="gemini/x"), RouteSetting(route="groq/y")]
    assert parsed.ai_bulk == [RouteSetting(route="gemini/z", reasoning_effort="high")]


async def test_each_route_sends_its_own_effort_or_none(
    make_client: MakeClient, fake_llm: FakeLLM, user_a: User
) -> None:
    client = make_client(
        ai_smart=[
            RouteSetting(route=f"gemini/{GEMINI_FLASH}", reasoning_effort="low"),
            RouteSetting(route=f"groq/{GPT_OSS}", reasoning_effort="minimal"),
            RouteSetting(route=f"groq/{QWEN}", reasoning_effort="low"),
        ],
        ai_daily_budget={},
    )
    fake_llm.reply(GEMINI_FLASH, httpx.Response(401))
    fake_llm.reply(GPT_OSS, httpx.Response(401))
    fake_llm.reply(QWEN, ok("qwen"))

    await client.complete_text("smart", MESSAGES, purpose="t", user_id=user_a.id)

    assert sent_effort(fake_llm) == ["low", "low", None]
    assert "reasoning_effort" not in fake_llm.requests[2].body


async def test_a_call_can_ask_for_more_thinking(
    make_client: MakeClient, fake_llm: FakeLLM, user_a: User
) -> None:
    client = make_client(ai_bulk=routes(f"gemini/{GEMINI_LITE}", effort="minimal"))
    fake_llm.reply(GEMINI_LITE, ok("a"), ok('{"topics": []}'))

    await client.complete_text(
        "bulk", MESSAGES, purpose="t", user_id=user_a.id, reasoning_effort="high"
    )
    await client.complete_text("bulk", MESSAGES, purpose="t", user_id=user_a.id)

    assert sent_effort(fake_llm) == ["high", "minimal"]


async def test_the_ping_always_asks_for_minimal(
    make_client: MakeClient, fake_llm: FakeLLM, user_a: User
) -> None:
    client = make_client(
        ai_smart=routes(f"gemini/{GEMINI_FLASH}", f"groq/{GPT_OSS}", f"groq/{QWEN}", effort="high"),
        ai_bulk=[],
    )
    for model in (GEMINI_FLASH, GPT_OSS, QWEN):
        fake_llm.reply(model, ok("pong"))

    for route in all_routes(client.settings):
        await client.ping(route, user_id=user_a.id)

    assert sent_effort(fake_llm) == ["minimal", "low", None]


# --- timeouts ---


def test_connect_and_read_timeouts_come_from_config(make_client: MakeClient) -> None:
    timeout = make_client()._http.timeout

    assert (timeout.connect, timeout.read) == (10.0, 90.0)


async def test_a_timeout_is_logged_retried_then_falls_through(
    make_client: MakeClient,
    fake_llm: FakeLLM,
    sleeps: Sleeps,
    session: AsyncSession,
    user_a: User,
) -> None:
    fake_llm.reply("flash", httpx.ReadTimeout("slow"), httpx.ConnectTimeout("no route"))
    fake_llm.reply("oss-120b", ok("From Groq"))

    text = await make_client().complete_text("smart", MESSAGES, purpose="t", user_id=user_a.id)

    assert text == "From Groq"
    assert sleeps.seconds == [2.0]  # retryable: backed off once
    outcomes = sorted(
        await session.scalars(select(AIUsage.outcome).where(AIUsage.user_id == user_a.id))
    )
    assert outcomes == ["ok", "timeout", "timeout"]


async def test_timeouts_count_against_the_budget(
    make_client: MakeClient, fake_llm: FakeLLM, session: AsyncSession, user_a: User
) -> None:
    session.add_all(
        AIUsage(
            user_id=user_a.id,
            provider="gemini",
            model="flash",
            role="smart",
            purpose="earlier",
            latency_ms=90_000,
            outcome="timeout",
        )
        for _ in range(3)  # flash's whole budget
    )
    await session.commit()
    fake_llm.reply("oss-120b", ok("Groq"))

    await make_client().complete_text("smart", MESSAGES, purpose="t", user_id=user_a.id)

    assert [sent.model for sent in fake_llm.requests] == ["oss-120b"]


async def test_a_slow_model_trips_the_ping_limit_and_the_rest_still_run(
    make_client: MakeClient, fake_llm: FakeLLM, session: AsyncSession, user_a: User
) -> None:
    client = make_client()
    fake_llm.slow("flash", 5.0)
    fake_llm.reply("flash", ok("too late"))
    fake_llm.reply("oss-120b", ok("pong"))
    out = io.StringIO()

    failures = await run_pings(
        client, routes_for("smart", client.settings), user_id=user_a.id, out=out, limit_seconds=0.2
    )

    lines = out.getvalue().splitlines()
    assert failures == 1
    assert lines[0].startswith("→ gemini/flash … FAIL after 0.")
    assert "timed out waiting for a reply" in lines[0]
    assert lines[1].startswith("→ groq/oss-120b … ok ")
    assert lines[1].endswith(": pong")
    outcomes = sorted(
        await session.scalars(select(AIUsage.outcome).where(AIUsage.purpose == "ping"))
    )
    assert outcomes == ["ok", "timeout"]
