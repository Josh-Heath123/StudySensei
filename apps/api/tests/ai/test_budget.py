"""Quota windows: midnight Pacific for Gemini (across daylight saving), UTC for Groq."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import httpx

from app.ai.adapter import retry_after_seconds
from app.ai.budget import next_reset, quota_zone, window_start
from app.ai.routes import ROLES, parse_route_key, routes_for
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

    assert smart[0].key == "gemini/gemini-3.8-flash"
    assert bulk[0].key == "gemini/gemini-3.5-flash-lite"
    assert all(r.daily_budget is not None for r in smart + bulk)
    assert not any(r.configured for r in smart + bulk)  # tests have no keys
    assert any(r.vision and r.provider.name == "groq" for r in smart)


def test_ollama_is_last_in_every_role_with_no_budget() -> None:
    settings = get_settings().model_copy(update={"ollama_model": "llama3.2"})

    for role in ROLES:
        last = routes_for(role, settings)[-1]
        assert (last.key, last.daily_budget, last.configured) == ("ollama/llama3.2", None, True)


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
