"""The shared replay fixture, against the server's timeline.

The same file is run by the browser engine's tests (apps/web/src/session-engine/
timer.test.ts), so the two implementations can't drift apart.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.services.errors import Invalid
from app.services.sessions.timeline import Event, replay

FIXTURE = Path(__file__).resolve().parents[4] / "fixtures" / "session-timelines.json"
DATA: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
T0 = datetime.fromisoformat(DATA["t0"])


def at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


def offset(seconds: float | None) -> datetime | None:
    return None if seconds is None else at(seconds)


@pytest.mark.parametrize("case", DATA["cases"], ids=[case["name"] for case in DATA["cases"]])
def test_server_replay_matches_the_shared_fixture(case: dict[str, Any]) -> None:
    events = [Event(e["type"], at(e["at"]), e["seq"]) for e in case["events"]]
    expect = case["expect"]

    if expect.get("invalid"):
        with pytest.raises(Invalid):
            replay(events)
        return

    timeline = replay(events)
    assert timeline.state == expect["state"]
    assert timeline.active_seconds == pytest.approx(expect["active_seconds"], abs=1e-6)
    assert timeline.break_seconds == pytest.approx(expect["break_seconds"], abs=1e-6)
    assert timeline.last_event_at == offset(expect["last_event_at"])
    assert timeline.ended_at == offset(expect["ended_at"])


def test_the_fixture_covers_valid_and_invalid_logs() -> None:
    kinds = {bool(case["expect"].get("invalid")) for case in DATA["cases"]}
    assert kinds == {True, False}
