"""Moving a block (decision 0022): the pure rules one at a time, and a Hypothesis property:
after any move check_move accepts, re-planning with the moved block pinned (fixed) keeps
every plan property."""

from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from hypothesis import event, given
from hypothesis import strategies as st

from app.services.planning import explain
from app.services.planning.availability import Interval
from app.services.planning.moves import MoveProblem, check_move, moved
from app.services.planning.planner import Block, PlanInput, plan
from tests.planning.plan_checks import check_plan
from tests.planning.test_plan_properties import PROPERTY_SETTINGS, plan_inputs

SAST = ZoneInfo("Africa/Johannesburg")
NOW = datetime(2026, 11, 23, 8, 0, tzinfo=SAST)  # Monday
MODULE, TEST, TOPIC = UUID(int=1), UUID(int=2), UUID(int=3)
DUE = datetime(2026, 11, 30, 9, 0, tzinfo=SAST)


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return NOW.replace(hour=hour, minute=minute) + timedelta(days=day)


def evenings(days: int = 7) -> tuple[Interval, ...]:
    return tuple(Interval(at(d, 18), at(d, 21)) for d in range(days))


def block(day: int, hour: int, minute: int = 0) -> Block:
    start = at(day, hour, minute)
    return Block(start, start + timedelta(minutes=50), MODULE, TEST, TOPIC, "study", "workload")


def check(
    target: datetime,
    *,
    the_block: Block | None = None,
    others: tuple[Block, ...] = (),
    cap: int = 180,
    studied_today: int = 0,
    free: tuple[Interval, ...] | None = None,
) -> MoveProblem | None:
    return check_move(
        the_block or block(1, 18),
        target,
        now=NOW,
        free=evenings() if free is None else free,
        neighbours=others,
        booked=others,
        due_at=DUE,
        daily_cap_minutes=cap,
        studied_on={NOW.date(): studied_today} if studied_today else {},
        timezone=SAST,
    )


def test_a_valid_move_has_no_problem() -> None:
    assert check(at(2, 19)) is None
    assert moved(block(1, 18), at(2, 19)).end == at(2, 19, 50)


def test_past() -> None:
    assert check(NOW - timedelta(hours=1)) == MoveProblem("past", (NOW - timedelta(hours=1)).date())


@pytest.mark.parametrize(
    "target",
    [
        at(2, 17, 55),  # starts before the window
        at(2, 20, 15),  # ends after it
        at(2, 10),  # no window that morning
    ],
)
def test_outside_free_time(target: datetime) -> None:
    assert check(target) == MoveProblem("outside_free_time", target.date())


def test_a_window_doesnt_run_into_the_next_local_day() -> None:
    late = (Interval(at(1, 23), at(2, 0)), Interval(at(2, 0), at(2, 1)))
    assert check(at(1, 23, 30), free=late) == MoveProblem("outside_free_time", at(1, 23).date())


def test_too_close() -> None:
    other = block(2, 18)  # 18:00-18:50
    assert check(at(2, 18, 55), others=(other,)) == MoveProblem("too_close", at(2, 0).date())
    assert check(at(2, 19), others=(other,)) is None  # exactly the break


def test_after_deadline() -> None:
    late_free = evenings(10)
    target = at(6, 18) + timedelta(days=1)  # 30 Nov 18:00, after 09:00
    assert check(target, free=late_free) == MoveProblem("after_deadline", target.date(), DUE)


def test_over_cap() -> None:
    others = (block(2, 18), block(2, 20))
    assert check(at(2, 19, 5), others=others, cap=180) == MoveProblem("too_close", at(2, 0).date())
    two = (block(2, 18),)
    assert check(at(2, 19, 0), others=two, cap=100) is None  # 50 + 50
    assert check(at(2, 19, 0), others=two, cap=90) == MoveProblem("over_cap", at(2, 0).date())


def test_a_final_review_stays_in_its_last_3_days() -> None:
    review = Block(at(5, 18), at(5, 18, 50), MODULE, TEST, None, "review", "final_review")
    # 30 Nov 09:00 due: the window opens 27 Nov 09:00.
    assert check(at(4, 18), the_block=review) is None  # 27 Nov 18:00
    assert check(at(3, 18), the_block=review) == MoveProblem("review_window", at(3, 0).date(), DUE)


def test_todays_studied_minutes_count_for_the_cap() -> None:
    today = at(0, 18)
    assert check(today, cap=120) is None
    assert check(today, cap=120, studied_today=80) == MoveProblem("over_cap", NOW.date())


@pytest.mark.parametrize(
    ("problem", "text"),
    [
        (MoveProblem("past", NOW.date()), "That time has passed."),
        (
            MoveProblem("outside_free_time", at(1, 0).date()),
            "That's outside your study time on Tue 24 Nov.",
        ),
        (MoveProblem("too_close", NOW.date()), "Leave 10 minutes between blocks."),
        (
            MoveProblem("after_deadline", DUE.date(), DUE),
            "That's after COS330 Exam (30 Nov, 09:00).",
        ),
        (MoveProblem("over_cap", at(1, 0).date()), "Tue 24 Nov would go over your 3 h daily cap."),
        (
            MoveProblem("review_window", NOW.date(), DUE),
            "A final review stays in the 3 days before COS330 Exam.",
        ),
    ],
)
def test_each_problem_in_words(problem: MoveProblem, text: str) -> None:
    assert (
        explain.move_problem_text(problem, assessment="COS330 Exam", cap=180, timezone=SAST) == text
    )


# --- the property ----------------------------------------------------------------------


@PROPERTY_SETTINGS
@given(st.one_of(plan_inputs(), plan_inputs(roomy=True)), st.data())
def test_an_accepted_move_keeps_every_plan_property(
    request: PlanInput, data: st.DataObject
) -> None:
    result = plan(request)
    movable = [b for b in result.blocks if b not in request.fixed]
    if not movable:
        return
    chosen = data.draw(st.sampled_from(movable))
    due = next(a.due_at for a in request.assessments if a.id == chosen.assessment_id)
    ahead = [w for w in request.free if w.end > request.now and w.start < due]
    if ahead and data.draw(st.integers(0, 3)) > 0:
        # Mostly somewhere in a free window still ahead, so moves are often accepted.
        window = data.draw(st.sampled_from(ahead))
        first = window.start.replace(second=0, microsecond=0)
        first += timedelta(minutes=-first.minute % 5)
        span = max(0, int((window.end - first).total_seconds() // 300))
        target = first + timedelta(minutes=5 * data.draw(st.integers(0, span)))
    else:
        first = request.now.replace(second=0, microsecond=0) - timedelta(hours=2)
        first -= timedelta(minutes=first.minute % 5)
        target = first + timedelta(minutes=5 * data.draw(st.integers(0, 22 * 24 * 12)))
    others = tuple(b for b in result.blocks if b != chosen)
    problem = check_move(
        chosen,
        target,
        now=request.now,
        free=request.free,
        neighbours=others,
        booked=others,
        due_at=due,
        daily_cap_minutes=request.daily_cap_minutes,
        studied_on=request.studied_on,
        timezone=request.timezone,
    )
    event(f"move: {problem.kind if problem else 'accepted'}")
    if problem is not None:
        return
    pinned = moved(chosen, target)
    again = replace(request, fixed=(*request.fixed, pinned))
    replanned = plan(again)
    check_plan(again, replanned)
    assert pinned in replanned.blocks
