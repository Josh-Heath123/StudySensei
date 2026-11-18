"""The ping CLI's lines, built from the structured results the endpoint also returns."""

from datetime import UTC, datetime

from app.ai.ping import PingOutcome, format_outcome
from app.ai.routes import routes_for
from app.core.config import Settings


def test_each_status_prints_one_line(settings: Settings) -> None:
    flash = routes_for("smart", settings)[0]

    ok = PingOutcome(flash, "ok", latency_ms=812, reply="pong\n", listed=True)
    failed = PingOutcome(
        flash, "failed", latency_ms=1234, error="gemini: HTTP 401: bad key", listed=True
    )
    resets = datetime(2026, 11, 19, 8, 0, tzinfo=UTC)
    skipped = PingOutcome(flash, "skipped", resets_at=resets, listed=False)
    unlisted = PingOutcome(flash, "ok", latency_ms=5, reply="pong", list_error="gemini: HTTP 500")

    assert format_outcome(ok) == "→ gemini/flash … ok 812 ms: pong"
    assert format_outcome(failed) == (
        "→ gemini/flash … FAIL after 1.2 s: gemini: HTTP 401: bad key"
    )
    assert format_outcome(skipped) == (
        "→ gemini/flash … skipped: budget used up until 2026-11-19 08:00 UTC (NOT in /models)"
    )
    assert format_outcome(unlisted).endswith("(/models failed: gemini: HTTP 500)")
