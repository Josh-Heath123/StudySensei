"""The planner's rules one at a time, with small hand-made inputs (decision 0017)."""

from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from app.services.planning.availability import Interval
from app.services.planning.planner import (
    AssessmentInput,
    Plan,
    PlanInput,
    TopicInput,
    plan,
    required_minutes,
)
from tests.planning.plan_checks import check_plan

UTC_ZONE = ZoneInfo("UTC")
MODULE = UUID(int=900)
NOW = datetime(2026, 11, 23, 6, 0, tzinfo=UTC)  # a Monday


def at(day: int, hour: int, minute: int = 0) -> datetime:
    """``day`` days after NOW's date, at hour:minute UTC."""
    return datetime(2026, 11, 23, hour, minute, tzinfo=UTC) + timedelta(days=day)


def topic(n: int, workload: int | None = 100, confidence: int | None = None) -> TopicInput:
    return TopicInput(UUID(int=n), MODULE, workload, confidence)


def exam(n: int, due: datetime, *topics: int, weight: float | None = None) -> AssessmentInput:
    return AssessmentInput(
        UUID(int=100 + n), MODULE, due, weight, tuple(UUID(int=t) for t in topics)
    )


def evenings(days: int, start: int = 18, end: int = 21) -> tuple[Interval, ...]:
    return tuple(Interval(at(d, start), at(d, end)) for d in range(days))


def make(
    *,
    free: tuple[Interval, ...],
    assessments: tuple[AssessmentInput, ...],
    topics: tuple[TopicInput, ...],
    cap: int = 600,
    studied: dict[UUID, int] | None = None,
) -> tuple[PlanInput, Plan]:
    request = PlanInput(NOW, free, cap, UTC_ZONE, assessments, topics, studied or {})
    result = plan(request)
    check_plan(request, result)
    return request, result


def study_blocks(result: Plan, n: int) -> list[tuple[datetime, int]]:
    return [(b.start, b.minutes) for b in result.blocks if b.topic_id == UUID(int=n)]


# --- required minutes ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [(1, 150), (2, 125), (3, 100), (None, 100), (4, 85), (5, 70)],
)
def test_lower_confidence_adds_time(confidence: int | None, expected: int) -> None:
    assert required_minutes(topic(1, 100, confidence), 0) == expected


def test_measured_minutes_come_off_first_and_the_result_rounds_up_to_5() -> None:
    assert required_minutes(topic(1, 100, 4), 40) == 55  # 60 at 85 % = 51, up to 55
    assert required_minutes(topic(1, 100, 1), 100) == 0
    assert required_minutes(topic(1, 100, 1), 500) == 0


def test_no_estimate_means_two_blocks_less_what_was_studied() -> None:
    assert required_minutes(topic(1, None), 0) == 100
    assert required_minutes(topic(1, None), 60) == 40
    assert required_minutes(topic(1, None), 120) == 0


# --- blocks --------------------------------------------------------------------------------


def test_a_25_minute_block_only_where_no_50_fits() -> None:
    # 18:00-19:30: one 50, the 10-minute break, then 30 minutes → one 25.
    free = tuple(Interval(at(d, 18), at(d, 19, 30)) for d in range(3))
    _, result = make(free=free, assessments=(exam(1, at(5, 9), 1),), topics=(topic(1, 600),))
    lengths = [b.minutes for b in result.blocks if b.start.date() == at(0, 0).date()]
    assert lengths == [50, 25]


def test_the_daily_cap_and_the_break_between_blocks() -> None:
    _, result = make(
        free=(Interval(at(1, 9), at(1, 17)),),
        assessments=(exam(1, at(9, 9), 1),),
        topics=(topic(1, 1000),),
        cap=120,
    )
    starts = [b.start for b in result.blocks]
    assert [s.hour * 60 + s.minute for s in starts] == [9 * 60, 10 * 60]  # 50 + 50 ≤ 120
    assert sum(b.minutes for b in result.blocks) == 100


def test_nothing_in_the_past_and_odd_times_start_on_the_5_minute_grid() -> None:
    request = PlanInput(
        NOW.replace(hour=18, minute=2, second=30),
        (Interval(at(0, 17), at(0, 22)),),
        600,
        UTC_ZONE,
        (exam(1, at(0, 23), 1),),
        (topic(1, 50),),
        {},
    )
    result = plan(request)
    check_plan(request, result)
    assert result.blocks[0].start == at(0, 18, 5)


# --- priority, spacing and review ------------------------------------------------------------


def test_sooner_deadlines_then_higher_weight_then_lower_confidence_go_first() -> None:
    # Room for exactly one block a day; each topic needs only its two minimum blocks.
    free = tuple(Interval(at(d, 18), at(d, 18, 50)) for d in range(1, 12))
    assessments = (
        exam(1, at(12, 9), 1, weight=10),
        exam(2, at(12, 9), 2, weight=60),
        exam(3, at(8, 9), 3, 4),
    )
    topics = (topic(1, 50), topic(2, 50), topic(3, 50, 5), topic(4, 50, 1))
    _, result = make(free=free, assessments=assessments, topics=topics)
    order = [b.topic_id.int for b in result.blocks if b.topic_id is not None]
    # Exam 3 first (sooner), its confidence-1 topic before its confidence-5 one; then exam 2
    # (weight 60) before exam 1 (weight 10).
    assert order[:4] == [4, 3, 4, 3]
    assert order.index(2) < order.index(1)


def test_two_blocks_on_different_days_and_no_back_to_back_when_there_is_a_choice() -> None:
    _, result = make(
        free=evenings(6),
        assessments=(exam(1, at(7, 9), 1, 2),),
        topics=(topic(1, 200), topic(2, 200)),
    )
    for n in (1, 2):
        blocks = study_blocks(result, n)
        assert len({start.date() for start, _ in blocks}) >= 2
    study = [b for b in result.blocks if b.kind == "study"]
    for before, after in pairwise(study):
        if before.start.date() == after.start.date():
            assert before.topic_id != after.topic_id, (before, after)


def test_the_final_review_is_as_late_as_fits_in_the_last_3_days() -> None:
    _, result = make(
        free=evenings(10),
        assessments=(exam(1, at(9, 9), 1),),
        topics=(topic(1, 100),),
    )
    reviews = [b for b in result.blocks if b.kind == "review"]
    assert len(reviews) == 1
    assert reviews[0].start == at(8, 20, 10)  # the last evening, at its end
    assert reviews[0].reason == "final_review" and reviews[0].topic_id is None


def test_a_topic_in_two_assessments_is_planned_for_the_sooner_one() -> None:
    _, result = make(
        free=evenings(14),
        assessments=(exam(1, at(13, 9), 1), exam(2, at(6, 9), 1)),
        topics=(topic(1, 100),),
    )
    study = [b for b in result.blocks if b.kind == "study"]
    assert {b.assessment_id for b in study} == {UUID(int=102)}
    assert all(b.end <= at(6, 9) for b in study)
    assert len([b for b in result.blocks if b.kind == "review"]) == 2


def test_reasons() -> None:
    _, result = make(
        free=evenings(20),
        assessments=(exam(1, at(19, 9), 1, 2, 3),),
        topics=(topic(1, 300, 1), topic(2, None), topic(3, 300, 4)),
    )
    reasons = {n: [b.reason for b in result.blocks if b.topic_id == UUID(int=n)] for n in (1, 2, 3)}
    assert reasons[1][:2] == ["low_confidence", "spacing"]
    assert reasons[2] == ["no_estimate", "spacing"]
    assert set(reasons[3]) == {"workload", "spacing"}  # all more than 7 days out
    _, soon = make(
        free=evenings(5), assessments=(exam(1, at(4, 9), 3),), topics=(topic(3, 300, 4),)
    )
    assert {b.reason for b in soon.blocks if b.kind == "study"} == {"urgency", "spacing"}


# --- shortfalls -----------------------------------------------------------------------------


def test_shortfalls_for_no_time_no_estimate_no_review_and_no_topics() -> None:
    _, result = make(
        free=(Interval(at(0, 18), at(0, 18, 50)),),  # one block, five days before the exam
        assessments=(exam(1, at(5, 9), 1, 2), exam(2, at(6, 9))),
        topics=(topic(1, 300), topic(2, None)),
    )
    kinds = {(s.kind, s.topic_id.int if s.topic_id else None) for s in result.shortfalls}
    assert ("no_topics", None) in kinds
    assert ("no_review_time", None) in kinds
    assert {("not_enough_time", 1), ("not_spaced", 1)} <= kinds
    assert {("no_estimate", 2), ("not_enough_time", 2), ("not_spaced", 2)} <= kinds
    short = next(
        s for s in result.shortfalls if s.kind == "not_enough_time" and s.topic_id == UUID(int=2)
    )
    assert (short.required_minutes, short.scheduled_minutes) == (100, 0)


def test_past_assessments_and_finished_topics_plan_nothing() -> None:
    _, result = make(
        free=evenings(5),
        assessments=(exam(1, NOW - timedelta(hours=1), 1), exam(2, at(4, 9), 2)),
        topics=(topic(1, 100), topic(2, 100)),
        studied={UUID(int=2): 100},
    )
    assert [b.kind for b in result.blocks] == ["review"]
    assert result.shortfalls == ()


def test_free_time_over_local_midnight_is_split_by_local_day() -> None:
    sast = ZoneInfo("Africa/Johannesburg")  # UTC+2: 21:00-02:00 UTC is 23:00-04:00 local
    request = PlanInput(
        NOW,
        (Interval(at(1, 21), at(2, 2)),),
        100,
        sast,
        (exam(1, at(6, 9), 1),),
        (topic(1, 1000),),
        {},
    )
    result = plan(request)
    check_plan(request, result)
    days: dict[date, int] = {}
    for b in result.blocks:
        local = b.start.astimezone(sast).date()
        days[local] = days.get(local, 0) + b.minutes
    # 23:00-24:00 local: one 50; 00:00-04:00 local: the cap (100), the first block after
    # the 10-minute break that follows 23:50.
    assert sorted(days.values()) == [50, 100]
    assert result.blocks[1].start == at(1, 22)


# --- decision 0019: course order and assessment kinds ------------------------------------


def test_equal_topics_start_in_course_order_not_id_order() -> None:
    # Four unrated chapters in one exam; their ids run against the course order.
    chapters = {"Ch1": 4, "Ch2": 1, "Ch3": 3, "Ch4": 2}
    topics = tuple(
        TopicInput(UUID(int=n), MODULE, 300, None, order=index)
        for index, n in enumerate(chapters.values())
    )
    test = exam(1, at(14, 9), *chapters.values())
    _, result = make(free=evenings(14), assessments=(test,), topics=topics, cap=180)

    first: dict[UUID, datetime] = {}
    for block in result.blocks:
        if block.topic_id is not None:
            first.setdefault(block.topic_id, block.start)
    names = {UUID(int=n): name for name, n in chapters.items()}
    assert [names[t] for t in sorted(first, key=lambda t: first[t])] == [
        "Ch1",
        "Ch2",
        "Ch3",
        "Ch4",
    ]


def test_lower_confidence_still_comes_before_course_order() -> None:
    topics = (
        TopicInput(UUID(int=1), MODULE, 100, None, order=0),
        TopicInput(UUID(int=2), MODULE, 100, 1, order=1),
    )
    _, result = make(
        free=evenings(10), assessments=(exam(1, at(10, 9), 1, 2),), topics=topics, cap=180
    )
    studied = [b.topic_id for b in result.blocks if b.topic_id is not None]
    assert studied[0] == UUID(int=2)


@pytest.mark.parametrize(
    ("kind", "reviewed"),
    [
        ("exam", True),
        ("test", True),
        ("quiz", True),
        ("assignment", False),
        ("project", False),
        ("other", False),
    ],
)
def test_only_exams_tests_and_quizzes_get_a_final_review(kind: str, reviewed: bool) -> None:
    due = at(6, 9)
    assessment = AssessmentInput(UUID(int=101), MODULE, due, None, (UUID(int=1),), kind)
    _, result = make(free=evenings(6), assessments=(assessment,), topics=(topic(1),))
    assert any(b.kind == "review" for b in result.blocks) == reviewed
    # Its topics are still studied either way.
    assert study_blocks(result, 1)


@pytest.mark.parametrize("kind", ["assignment", "project", "other"])
def test_no_review_time_is_never_reported_for_an_unreviewed_kind(kind: str) -> None:
    # Free time only on the first two days: nothing in the last 3 days before the deadline.
    assessment = AssessmentInput(UUID(int=101), MODULE, at(8, 9), None, (UUID(int=1),), kind)
    _, result = make(free=evenings(2), assessments=(assessment,), topics=(topic(1),))
    assert not [s for s in result.shortfalls if s.kind == "no_review_time"]
    exam_like = AssessmentInput(UUID(int=101), MODULE, at(8, 9), None, (UUID(int=1),), "exam")
    _, result = make(free=evenings(2), assessments=(exam_like,), topics=(topic(1),))
    assert [s.kind for s in result.shortfalls if s.kind == "no_review_time"] == ["no_review_time"]


# --- decision 0020: spreading a single unit's blocks ---------------------------------------


def test_a_single_units_blocks_spread_over_its_evenings() -> None:
    # One unit needing six 50-minute blocks, and four 3-hour evenings: its two spacing blocks
    # take the first two, and the other four must not stack on one evening.
    unit = topic(1, workload=300)
    task = AssessmentInput(UUID(int=101), MODULE, at(4, 9), None, (unit.id,), "assignment")
    request, result = make(free=evenings(4), assessments=(task,), topics=(unit,), cap=180)

    per_day: dict[date, int] = {}
    for block in result.blocks:
        day = block.start.astimezone(request.timezone).date()
        per_day[day] = per_day.get(day, 0) + 1
    assert sum(per_day.values()) == 6
    assert max(per_day.values()) <= 2
    assert max(per_day.values()) - min(per_day.values()) <= 1
    assert len(per_day) == 4
