"""Replay a study session's events into its state and totals.

The event log is the source of truth: the client never sends durations. This
module is pure (no database, no clock), so the same events always give the
same answer and the numbers can be rebuilt at any time.

    (none) --start--> active
    active --pause--> paused --resume--> active
    active --break_start--> on_break --break_end--> active
    active | paused | on_break --end--> ended

Totals run up to the *last event*, never to "now": the server clock and the
client clock never mix. A live timer adds ``now - last_event_at`` itself while
the state is ``active`` or ``on_break``.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.services.errors import Invalid

EventType = Literal["start", "pause", "resume", "break_start", "break_end", "end"]
State = Literal["active", "paused", "on_break", "ended"]

EVENT_TYPES: tuple[EventType, ...] = ("start", "pause", "resume", "break_start", "break_end", "end")
STATES: tuple[State, ...] = ("active", "paused", "on_break", "ended")

# (state before, event) -> state after. Anything missing is illegal.
TRANSITIONS: dict[tuple[State, EventType], State] = {
    ("active", "pause"): "paused",
    ("paused", "resume"): "active",
    ("active", "break_start"): "on_break",
    ("on_break", "break_end"): "active",
    ("active", "end"): "ended",
    ("paused", "end"): "ended",
    ("on_break", "end"): "ended",
}


@dataclass(frozen=True)
class Event:
    type: EventType
    occurred_at: datetime
    # Tie-break for equal timestamps: the order the server received them in.
    seq: int


@dataclass(frozen=True)
class Timeline:
    state: State
    started_at: datetime
    ended_at: datetime | None
    last_event_at: datetime
    active_seconds: float
    break_seconds: float


def replay(events: Iterable[Event]) -> Timeline:
    """Sort by (occurred_at, seq) and walk the state machine. Raises ``Invalid``."""
    ordered = sorted(events, key=lambda e: (e.occurred_at, e.seq))
    if not ordered:
        raise Invalid("A session needs a start event")
    first, rest = ordered[0], ordered[1:]
    if first.type != "start":
        raise Invalid(f"No event can come before the session's start ({first.type})")

    state: State = "active"
    since = first.occurred_at
    active = breaks = 0.0
    for event in rest:
        if state == "ended":
            raise Invalid(f"The session has ended; {event.type} can't come after it")
        after = TRANSITIONS.get((state, event.type))
        if after is None:
            raise Invalid(f"Can't {event.type} while {state}")
        elapsed = (event.occurred_at - since).total_seconds()
        if state == "active":
            active += elapsed
        elif state == "on_break":
            breaks += elapsed
        state, since = after, event.occurred_at

    return Timeline(
        state=state,
        started_at=first.occurred_at,
        ended_at=since if state == "ended" else None,
        last_event_at=since,
        active_seconds=active,
        break_seconds=breaks,
    )
