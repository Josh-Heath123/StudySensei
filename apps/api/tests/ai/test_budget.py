"""Quota windows: midnight Pacific for Gemini (across daylight saving), UTC for Groq."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import httpx

from app.ai.adapter import retry_after_seconds
from app.ai.budget import next_reset, quota_zone, window_start
from app.ai.routes import parse_route_key, routes_for
from app.core.config import get_settings

PACIFIC = ZoneInfo("America/Los_Angeles")


def test_gemini_resets_at_midnight_pacific() -> None:
    zone = quota_zone("gemini", get_settings())
    # 07:59 UTC on 17 Nov is 23:59 on the 16th in California (PST, UTC-8).
    now = datetime(2026, 11, 17, 7, 59, tzinfo=UTC)

    assert window_start(now, zone) == datetime(2026, 11, 16, 8, 0, tzinfo=UTC)
    assert next_reset(now, zone) == datetime(2026, 11, 17, 8, 0, tzinfo=UTC)


def test_summer_time_moves_the_reset_an_hour() -> None:
    now = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)  # PDT, UTC-7

    assert next_reset(now, PACIFIC) == datetime(2026, 7, 2, 7, 0, tzinfo=UTC)


def test_the_day_clocks_change_is_23_hours_long() -> None:
    # US clocks went forward on 8 March 2026.
    now = datetime(2026, 3, 8, 12, 0, tzinfo=UTC)

    start, end = window_start(now, PACIFIC), next_reset(now, PACIFIC)

    assert (end - start).total_seconds() == 23 * 3600


def test_groq_resets_at_midnight_utc() -> None:
    zone = quota_zone("groq", get_settings())
    now = datetime(2026, 11, 17, 23, 30, tzinfo=UTC)

    assert next_reset(now, zone) == datetime(2026, 11, 18, tzinfo=UTC)


def test_route_keys_split_at_the_first_slash() -> None:
    assert parse_route_key("groq/openai/gpt-oss-120b") == ("groq", "openai/gpt-oss-120b")


def test_default_roles_and_budgets() -> None:
    settings = get_settings()

    smart = routes_for("smart", settings)
    bulk = routes_for("bulk", settings)
    vision = routes_for("vision", settings)

    # 3.8 Flash (~20 a day, slow) is only ever the last resort.
    assert [r.key for r in smart] == [
        "groq/openai/gpt-oss-120b",
        "gemini/gemini-3.5-flash-lite",
        "gemini/gemini-3.8-flash",
    ]
    assert [r.key for r in bulk] == ["gemini/gemini-3.5-flash-lite", "groq/openai/gpt-oss-20b"]
    assert [r.key for r in vision] == [
        "gemini/gemini-3.5-flash-lite",
        "groq/qwen/qwen3.8-27b",
        "gemini/gemini-3.8-flash",
    ]
    assert all(r.daily_budget is not None for r in smart + bulk + vision)
    assert not any(r.configured for r in smart + bulk + vision)  # tests have no keys
    assert all(r.vision for r in vision)
    assert not any(r.vision for r in smart if "gpt-oss" in r.model)  # text only


def test_ollama_is_last_in_the_text_roles_with_no_budget() -> None:
    settings = get_settings().model_copy(update={"ollama_model": "llama3.2"})

    for role in ("smart", "bulk"):
        last = routes_for(role, settings)[-1]
        assert (last.key, last.daily_budget, last.configured) == ("ollama/llama3.2", None, True)
    # A local model may not read images.
    assert all(r.provider.name != "ollama" for r in routes_for("vision", settings))


def test_retry_after_in_seconds_as_a_date_or_in_geminis_body() -> None:
    now = datetime(2026, 11, 17, 8, 0, tzinfo=UTC)

    assert retry_after_seconds(httpx.Response(429, headers={"Retry-After": "12"})) == 12.0
    dated = httpx.Response(429, headers={"Retry-After": "Tue, 17 Nov 2026 08:01:30 GMT"})
    assert retry_after_seconds(dated, now) == 90.0
    gemini = httpx.Response(
        429, json=[{"error": {"details": [{"retryDelay": "37s"}], "code": 429}}]
    )
    assert retry_after_seconds(gemini) == 37.0
    assert retry_after_seconds(httpx.Response(429)) is None
