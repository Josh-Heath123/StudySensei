"""FSRS scheduling (ADR 0026). Pure: a golden test against py-fsrs itself (the roadmap's "due
dates follow FSRS"), and properties with Hypothesis."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from fsrs import Card, Rating, Scheduler
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.practice.scheduling import (
    FSRS_VERSION,
    MemoryState,
    ReviewEvent,
    SchedulingSettings,
    interval_label,
    replay,
    retrievability,
    schedule,
)

T0 = datetime(2026, 11, 2, 8, 0, tzinfo=UTC)
DEFAULT = SchedulingSettings()

# (minutes after T0, grade): learning steps, a lapse, relearning and long reviews.
LOG = [
    (0, 3),
    (10, 3),
    (60 * 24 * 3, 3),
    (60 * 24 * 12, 2),
    (60 * 24 * 30, 1),
    (60 * 24 * 30 + 10, 3),
    (60 * 24 * 45, 4),
    (60 * 24 * 120, 3),
]


def test_due_dates_are_exactly_py_fsrs() -> None:
    """The golden test: the same timestamps and grades through py-fsrs directly (no fuzz)."""
    scheduler = Scheduler(desired_retention=0.9, enable_fuzzing=False)
    card = Card(card_id=1, due=T0)
    state: MemoryState | None = None
    for minutes, grade in LOG:
        at = T0 + timedelta(minutes=minutes)
        card, _ = scheduler.review_card(card, Rating(grade), review_datetime=at)
        state, days = schedule(state, grade, at, DEFAULT)
        assert state.due == card.due
        assert state.stability == card.stability
        assert state.difficulty == card.difficulty
        assert state.step == card.step
        assert state.state == card.state.name.lower()
        assert days == (card.due - at).days
    assert state is not None
    assert (state.reps, state.lapses) == (len(LOG), 1)


def test_the_first_review_of_a_new_item() -> None:
    again, days = schedule(None, 1, T0, DEFAULT)
    assert (again.state, again.step, again.due, days) == (
        "learning",
        0,
        T0 + timedelta(minutes=1),
        0,
    )
    good, _ = schedule(None, 3, T0, DEFAULT)
    assert (good.state, good.step, good.due) == ("learning", 1, T0 + timedelta(minutes=10))
    easy, days = schedule(None, 4, T0, DEFAULT)
    assert easy.state == "review" and easy.step is None and days >= 1
    assert FSRS_VERSION == "fsrs 6.3.3"


def test_a_naive_or_non_utc_time_is_converted_or_refused() -> None:
    sast = timezone(timedelta(hours=2))
    a, _ = schedule(None, 3, T0.astimezone(sast), DEFAULT)
    b, _ = schedule(None, 3, T0, DEFAULT)
    assert a == b
    with pytest.raises(ValueError):
        schedule(None, 3, T0.replace(tzinfo=None), DEFAULT)
    with pytest.raises(ValueError):
        schedule(None, 5, T0, DEFAULT)


def test_retention_changes_only_later_reviews() -> None:
    events = [ReviewEvent(3, T0, 0.9), ReviewEvent(3, T0 + timedelta(days=2), 0.9)]
    before = replay(events, DEFAULT)
    # Raising retention later leaves those reviews as they were, and shortens the next one.
    changed = [*events, ReviewEvent(3, T0 + timedelta(days=8), 0.97)]
    kept = [*events, ReviewEvent(3, T0 + timedelta(days=8), 0.9)]
    assert replay(changed[:2], DEFAULT) == before
    assert replay(changed, DEFAULT).due < replay(kept, DEFAULT).due  # type: ignore[union-attr]


def test_retrievability() -> None:
    assert retrievability(None, T0) is None
    state, _ = schedule(None, 4, T0, DEFAULT)
    assert retrievability(state, T0) == pytest.approx(1.0)
    later = retrievability(state, T0 + timedelta(days=30))
    assert later is not None and 0 < later < 1


@pytest.mark.parametrize(
    ("delta", "label"),
    [
        (timedelta(seconds=30), "1 min"),
        (timedelta(minutes=1), "1 min"),
        (timedelta(minutes=5, seconds=30), "6 min"),
        (timedelta(minutes=10), "10 min"),
        (timedelta(hours=3), "3 h"),
        (timedelta(days=1), "1 day"),
        (timedelta(days=4), "4 days"),
        (timedelta(days=45), "1.5 mo"),
        (timedelta(days=400), "1.1 yr"),
    ],
)
def test_interval_labels(delta: timedelta, label: str) -> None:
    assert interval_label(delta) == label


# --- properties --------------------------------------------------------------------------

grades = st.integers(min_value=1, max_value=4)
gaps = st.integers(min_value=0, max_value=60 * 24 * 200)  # minutes between reviews
retentions = st.sampled_from([0.8, 0.85, 0.9, 0.95, 0.97])
logs = st.lists(st.tuples(gaps, grades, retentions), min_size=1, max_size=12)


def events_of(log: list[tuple[int, int, float]]) -> list[ReviewEvent]:
    at, found = T0, []
    for gap, grade, retention in log:
        at += timedelta(minutes=gap)
        found.append(ReviewEvent(grade, at, retention))
    return found


def step_by_step(events: list[ReviewEvent]) -> MemoryState | None:
    state: MemoryState | None = None
    for event in events:
        state, _ = schedule(
            state, event.grade, event.at, SchedulingSettings(event.retention or 0.9)
        )
    return state


@settings(max_examples=300, deadline=None)
@given(logs)
def test_replay_equals_the_state_built_review_by_review(log: list[tuple[int, int, float]]) -> None:
    events = events_of(log)
    assert replay(events, DEFAULT) == step_by_step(events)


@settings(max_examples=300, deadline=None)
@given(logs, gaps)
def test_a_better_grade_is_never_due_sooner(log: list[tuple[int, int, float]], gap: int) -> None:
    events = events_of(log)
    prior = replay(events, DEFAULT)
    at = events[-1].at + timedelta(minutes=gap)
    dues = [schedule(prior, grade, at, DEFAULT)[0].due for grade in (1, 2, 3, 4)]
    assert dues == sorted(dues), dues


@settings(max_examples=300, deadline=None)
@given(logs, gaps, grades)
def test_due_is_always_after_the_review(
    log: list[tuple[int, int, float]], gap: int, grade: int
) -> None:
    prior = replay(events_of(log), DEFAULT)
    at = events_of(log)[-1].at + timedelta(minutes=gap)
    state, days = schedule(prior, grade, at, DEFAULT)
    assert state.due > at and state.last_review_at == at and days >= 0


@settings(max_examples=200, deadline=None)
@given(logs)
def test_the_same_inputs_give_the_same_output(log: list[tuple[int, int, float]]) -> None:
    events = events_of(log)
    assert replay(events, DEFAULT) == replay(list(events), DEFAULT)


@settings(max_examples=200, deadline=None)
@given(logs)
def test_snapshots_round_trip(log: list[tuple[int, int, float]]) -> None:
    state = replay(events_of(log), DEFAULT)
    assert state is not None
    assert MemoryState.from_snapshot(state.snapshot()) == state
