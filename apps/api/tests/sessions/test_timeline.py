"""The session timeline: a pure replay of events into state and totals."""

from datetime import UTC, datetime, timedelta

import pytest

from app.services.errors import Invalid
from app.services.sessions.timeline import Event, EventType, replay

T0 = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def log(*steps: tuple[EventType, float]) -> list[Event]:
    """Events from (type, minutes after T0), with seq in the order given."""
    return [Event(kind, at(minutes), seq) for seq, (kind, minutes) in enumerate(steps)]


def test_start_only_is_active_with_nothing_counted_yet() -> None:
    timeline = replay(log(("start", 0)))

    assert timeline.state == "active"
    assert timeline.started_at == T0
    assert timeline.ended_at is None
    assert timeline.last_event_at == T0
    assert (timeline.active_seconds, timeline.break_seconds) == (0, 0)


def test_start_then_end_counts_all_of_it_as_active() -> None:
    timeline = replay(log(("start", 0), ("end", 50)))

    assert timeline.state == "ended"
    assert timeline.ended_at == at(50)
    assert timeline.active_seconds == 50 * 60
    assert timeline.break_seconds == 0


def test_paused_time_counts_as_neither_active_nor_break() -> None:
    timeline = replay(
        log(("start", 0), ("pause", 10), ("resume", 15), ("pause", 20), ("resume", 21), ("end", 30))
    )

    assert timeline.active_seconds == (10 + 5 + 9) * 60
    assert timeline.break_seconds == 0


def test_break_time_is_counted_separately() -> None:
    timeline = replay(log(("start", 0), ("break_start", 25), ("break_end", 30), ("end", 55)))

    assert timeline.active_seconds == 50 * 60
    assert timeline.break_seconds == 5 * 60


def test_ending_during_a_break_closes_the_break() -> None:
    timeline = replay(log(("start", 0), ("break_start", 25), ("end", 32)))

    assert timeline.state == "ended"
    assert timeline.active_seconds == 25 * 60
    assert timeline.break_seconds == 7 * 60


def test_ending_while_paused_adds_nothing_after_the_pause() -> None:
    timeline = replay(log(("start", 0), ("pause", 10), ("end", 40)))

    assert timeline.active_seconds == 10 * 60
    assert timeline.break_seconds == 0


def test_totals_stop_at_the_last_event_of_an_open_session() -> None:
    # The client adds the live tail (now - last_event_at) on its own clock.
    timeline = replay(log(("start", 0), ("break_start", 25), ("break_end", 30)))

    assert timeline.state == "active"
    assert timeline.last_event_at == at(30)
    assert (timeline.active_seconds, timeline.break_seconds) == (25 * 60, 5 * 60)


def test_open_break_counts_up_to_the_last_event() -> None:
    timeline = replay(log(("start", 0), ("break_start", 25)))

    assert timeline.state == "on_break"
    assert (timeline.active_seconds, timeline.break_seconds) == (25 * 60, 0)


def test_sub_second_precision_is_kept() -> None:
    events = [
        Event("start", T0, 0),
        Event("pause", T0 + timedelta(seconds=1, milliseconds=250), 1),
    ]

    assert replay(events).active_seconds == 1.25


def test_out_of_order_events_are_replayed_in_time_order() -> None:
    # An offline batch can reach the server in any order.
    events = log(("end", 40), ("resume", 15), ("start", 0), ("pause", 10))

    timeline = replay(events)

    assert timeline.state == "ended"
    assert timeline.active_seconds == (10 + 25) * 60


def test_equal_timestamps_keep_their_seq_order() -> None:
    events = [Event("resume", at(10), 2), Event("pause", at(10), 1), Event("start", T0, 0)]

    timeline = replay(events)

    assert timeline.state == "active"
    assert timeline.active_seconds == 10 * 60


def test_an_empty_log_is_invalid() -> None:
    with pytest.raises(Invalid, match="start"):
        replay([])


def test_the_first_event_must_be_the_start() -> None:
    with pytest.raises(Invalid, match="before the session's start"):
        replay(log(("pause", 0), ("start", 1)))


def test_a_second_start_is_invalid() -> None:
    with pytest.raises(Invalid):
        replay(log(("start", 0), ("start", 5)))


def test_nothing_may_follow_the_end() -> None:
    with pytest.raises(Invalid, match="ended"):
        replay(log(("start", 0), ("end", 10), ("resume", 11)))


@pytest.mark.parametrize(
    "steps",
    [
        [("start", 0), ("resume", 1)],  # resume while active
        [("start", 0), ("break_end", 1)],  # break_end while active
        [("start", 0), ("pause", 1), ("pause", 2)],
        [("start", 0), ("pause", 1), ("break_start", 2)],  # break from paused
        [("start", 0), ("pause", 1), ("break_end", 2)],
        [("start", 0), ("break_start", 1), ("pause", 2)],  # pause during a break
        [("start", 0), ("break_start", 1), ("resume", 2)],
        [("start", 0), ("break_start", 1), ("break_start", 2)],
        [("start", 0), ("end", 1), ("end", 2)],
    ],
)
def test_illegal_transitions_are_rejected(steps: list[tuple[EventType, float]]) -> None:
    with pytest.raises(Invalid):
        replay(log(*steps))
