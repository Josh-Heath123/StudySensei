"""FSRS scheduling for practice items (ADR 0026). Pure: no database, no clock, no AI.

py-fsrs (``fsrs`` 6.3.3, MIT) does the maths: a ``Scheduler`` with its default parameters,
learning steps (1 min, 10 min) and relearning step (10 min), the user's desired retention,
and **fuzzing off**, so a due date is a function of the review log alone and can be checked
by replaying it. This module is the only place that calls it:

- ``schedule(state, grade, at, settings)``: one review. ``state`` None is a new item.
  Grades are FSRS's ratings: 1 Again, 2 Hard, 3 Good, 4 Easy.
- ``replay(events, settings)``: a whole log, in order. Each event carries the retention in
  force when it was made, so changing the setting changes only later reviews.
- ``retrievability``: FSRS's R (the estimated chance of recall) at a time.
- ``interval_label``: "1 min", "10 min", "1 day", "4 days" for a preview.

``reps`` counts reviews; ``lapses`` counts Again on an item in the review state (FSRS's
lapse). Both are ours: py-fsrs's ``Card`` doesn't keep them.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from importlib.metadata import version
from typing import Any, Literal

from fsrs import Card, Rating, Scheduler, State

FSRS_VERSION = f"fsrs {version('fsrs')}"
MemoryName = Literal["learning", "review", "relearning"]
_NAMES: dict[State, MemoryName] = {
    State.Learning: "learning",
    State.Review: "review",
    State.Relearning: "relearning",
}
_STATES = {name: state for state, name in _NAMES.items()}
# py-fsrs's Card wants an id; it's never used in scheduling (and a default one sleeps 1 ms).
_CARD_ID = 1


@dataclass(frozen=True)
class SchedulingSettings:
    desired_retention: float = 0.9


@dataclass(frozen=True)
class MemoryState:
    """An item's FSRS state after its latest review."""

    state: MemoryName
    # The learning or relearning step, or None in the review state.
    step: int | None
    stability: float
    difficulty: float
    due: datetime
    last_review_at: datetime
    reps: int
    lapses: int

    def snapshot(self) -> dict[str, Any]:
        """JSON for ``reviews.state_before`` / ``state_after``."""
        return {
            "state": self.state,
            "step": self.step,
            "stability": self.stability,
            "difficulty": self.difficulty,
            "due": self.due.isoformat(),
            "last_review_at": self.last_review_at.isoformat(),
            "reps": self.reps,
            "lapses": self.lapses,
        }

    @classmethod
    def from_snapshot(cls, data: dict[str, Any]) -> "MemoryState":
        return cls(
            state=data["state"],
            step=data["step"],
            stability=float(data["stability"]),
            difficulty=float(data["difficulty"]),
            due=datetime.fromisoformat(data["due"]),
            last_review_at=datetime.fromisoformat(data["last_review_at"]),
            reps=int(data["reps"]),
            lapses=int(data["lapses"]),
        )


@dataclass(frozen=True)
class ReviewEvent:
    """One review as replay needs it: the grade, when, and the retention then in force."""

    grade: int
    at: datetime
    retention: float | None = None


@lru_cache(maxsize=32)
def scheduler(desired_retention: float) -> Scheduler:
    return Scheduler(desired_retention=desired_retention, enable_fuzzing=False)


def _utc(at: datetime) -> datetime:
    if at.tzinfo is None:
        raise ValueError("A review time needs a timezone")
    # py-fsrs insists on timezone.utc itself, not just an offset of zero.
    return at.astimezone(UTC)


def _card(state: MemoryState | None, at: datetime) -> Card:
    if state is None:
        return Card(card_id=_CARD_ID, due=at)
    return Card(
        card_id=_CARD_ID,
        state=_STATES[state.state],
        step=state.step,
        stability=state.stability,
        difficulty=state.difficulty,
        due=_utc(state.due),
        last_review=_utc(state.last_review_at),
    )


def schedule(
    state: MemoryState | None, grade: int, at: datetime, settings: SchedulingSettings
) -> tuple[MemoryState, int]:
    """The state after reviewing at ``at`` with ``grade``, and the whole days until it's due."""
    if grade not in (1, 2, 3, 4):
        raise ValueError("A grade is 1 (again), 2 (hard), 3 (good) or 4 (easy)")
    at = _utc(at)
    card, _ = scheduler(settings.desired_retention).review_card(
        _card(state, at), Rating(grade), review_datetime=at
    )
    assert card.stability is not None and card.difficulty is not None
    lapsed = state is not None and state.state == "review" and grade == 1
    new = MemoryState(
        state=_NAMES[card.state],
        step=card.step,
        stability=card.stability,
        difficulty=card.difficulty,
        due=card.due,
        last_review_at=at,
        reps=(state.reps if state else 0) + 1,
        lapses=(state.lapses if state else 0) + (1 if lapsed else 0),
    )
    return new, (card.due - at).days


def replay(events: Sequence[ReviewEvent], settings: SchedulingSettings) -> MemoryState | None:
    """The state a review log leads to, in order (None for no reviews). An event without its
    own retention uses ``settings``."""
    state: MemoryState | None = None
    for event in events:
        retention = event.retention if event.retention is not None else settings.desired_retention
        state, _ = schedule(state, event.grade, event.at, SchedulingSettings(retention))
    return state


def retrievability(
    state: MemoryState | None, at: datetime, settings: SchedulingSettings | None = None
) -> float | None:
    """FSRS's R at ``at``: the estimated chance of recall (None for a new item)."""
    if state is None:
        return None
    retention = (settings or SchedulingSettings()).desired_retention
    return float(scheduler(retention).get_card_retrievability(_card(state, _utc(at)), _utc(at)))


def interval_label(delta: timedelta) -> str:
    """ "1 min", "10 min", "3 h", "1 day", "4 days", "1.5 mo", "1.1 yr"."""
    minutes = delta.total_seconds() / 60
    if minutes < 60:
        return f"{max(1, round(minutes))} min"
    hours = minutes / 60
    if hours < 24:
        return f"{round(hours)} h"
    days = round(hours / 24)
    if days < 30:
        return "1 day" if days == 1 else f"{days} days"
    if days < 365:
        return f"{days / 30:.1f} mo".replace(".0 ", " ")
    return f"{days / 365:.1f} yr".replace(".0 ", " ")
