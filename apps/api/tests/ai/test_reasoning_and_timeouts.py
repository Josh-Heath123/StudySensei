"""reasoning_effort per route and per call, timeouts, and the ping's own time limit."""

import io

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.adapter import MAX_PROVIDER_MESSAGE, ProviderError, http_error
from app.ai.messages import user
from app.ai.ping import run_pings
from app.ai.routes import all_routes, routes_for, wire_effort
from app.core.config import ReasoningEffort, RouteSetting, Settings, get_settings
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
    ("key", "effort", "sent"),
    [
        (f"gemini/{GEMINI_FLASH}", "minimal", "low"),  # 3.8 Flash has no "minimal"
        (f"gemini/{GEMINI_FLASH}", "low", "low"),
        (f"gemini/{GEMINI_FLASH}", None, None),
        (f"gemini/{GEMINI_LITE}", "minimal", "minimal"),
        (f"groq/{GPT_OSS}", "medium", "medium"),
        ("groq/openai/gpt-oss-20b", "minimal", "low"),  # nor has gpt-oss
        (f"groq/{QWEN}", "minimal", "low"),
        ("ollama/llama3.2", "low", None),  # not listed: never sent
    ],
)
def test_each_model_gets_a_level_it_supports(
    key: str, effort: ReasoningEffort | None, sent: str | None
) -> None:
    supported = get_settings().ai_reasoning_efforts.get(key, [])

    assert wire_effort(supported, effort) == sent


def test_an_unsupported_level_is_raised_to_the_next_one_up_or_the_highest() -> None:
    assert wire_effort(["low", "high"], "medium") == "high"
    assert wire_effort(["minimal", "low"], "high") == "low"
    assert wire_effort(["high", "low"], "minimal") == "low"  # order in config doesn't matter


def test_every_routed_model_has_its_levels_listed() -> None:
    defaults = get_settings()

    assert {r.key for r in all_routes(defaults)} == set(defaults.ai_reasoning_efforts)


def test_default_thinking_levels() -> None:
    defaults = get_settings()

    assert {r.key: r.reasoning_effort for r in routes_for("bulk", defaults)} == {
        f"gemini/{GEMINI_LITE}": "minimal",
        "groq/openai/gpt-oss-20b": "low",
    }
    assert {r.reasoning_effort for r in routes_for("smart", defaults)} == {"low"}
    assert {r.reasoning_effort for r in routes_for("vision", defaults)} == {"low"}


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

    assert sent_effort(fake_llm) == ["low", "low", "low"]


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
        ai_vision=[],
        ai_long=[],
    )
    for model in (GEMINI_FLASH, GPT_OSS, QWEN):
        fake_llm.reply(model, ok("pong"))

    for route in all_routes(client.settings):
        await client.ping(route, user_id=user_a.id)

    assert sent_effort(fake_llm) == ["low", "low", "low"]  # each model's lowest


async def test_ping_sends_minimal_to_flash_lite_and_low_to_flash(
    make_client: MakeClient, fake_llm: FakeLLM, user_a: User
) -> None:
    client = make_client(
        ai_smart=routes(f"gemini/{GEMINI_FLASH}"),
        ai_bulk=routes(f"gemini/{GEMINI_LITE}"),
        ai_vision=[],
        ai_long=[],
    )
    fake_llm.reply(GEMINI_FLASH, ok("pong"))
    fake_llm.reply(GEMINI_LITE, ok("pong"))

    for route in all_routes(client.settings):
        await client.ping(route, user_id=user_a.id)

    assert [(s.model, s.body["reasoning_effort"]) for s in fake_llm.requests] == [
        (GEMINI_FLASH, "low"),
        (GEMINI_LITE, "minimal"),
    ]


# --- provider error messages ---


async def test_a_400_carries_the_providers_message(
    make_client: MakeClient, fake_llm: FakeLLM, user_a: User
) -> None:
    client = make_client(ai_smart=routes(f"gemini/{GEMINI_FLASH}"), ai_bulk=[])
    body = [
        {
            "error": {
                "code": 400,
                "message": "Thinking level MINIMAL is not supported for this model.",
                "status": "INVALID_ARGUMENT",
            }
        }
    ]
    fake_llm.reply(GEMINI_FLASH, httpx.Response(400, json=body))

    with pytest.raises(ProviderError) as caught:
        await client.ping(client.routes("smart")[0], user_id=user_a.id)

    assert str(caught.value) == (
        "gemini: HTTP 400: Thinking level MINIMAL is not supported for this model."
    )


def test_only_the_message_is_taken_and_trimmed() -> None:
    long = httpx.Response(
        400,
        json={"error": {"message": "x" * 500, "param": "secret-prompt-text"}},
        headers={"x-goog-api-key": "a-key"},
    )
    message = http_error("groq", long)

    assert message.startswith("groq: HTTP 400: xxx")
    assert len(message.removeprefix("groq: HTTP 400: ")) == MAX_PROVIDER_MESSAGE
    assert "secret-prompt-text" not in message and "a-key" not in message
    assert http_error("groq", httpx.Response(503, text="<html>down</html>")) == "groq: HTTP 503"
    assert http_error("groq", httpx.Response(400, json={"error": "Bad model"})) == (
        "groq: HTTP 400: Bad model"
    )


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
