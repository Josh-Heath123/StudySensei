"""The feasibility report (decision 0018): Hypothesis properties over random plans, and a few
worked examples."""

from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from hypothesis import event, given
from hypothesis import strategies as st

from app.services.planning.availability import Interval
from app.services.planning.feasibility import TIGHT_PERCENT, feasibility, free_minutes, status
from app.services.planning.planner import (
    AssessmentInput,
    PlanInput,
    TopicInput,
    plan,
    required_minutes,
    scope,
)
from tests.planning.test_plan_properties import PROPERTY_SETTINGS, plan_inputs


@PROPERTY_SETTINGS
@given(st.one_of(plan_inputs(), plan_inputs(roomy=True)))
def test_the_report_agrees_with_the_plan(request: PlanInput) -> None:
    result = plan(request)
    report = feasibility(result, request)
    found = scope(request)
    topics_by_id = {t.id: t for t in request.topics}

    # One entry per upcoming assessment, in the planner's order.
    assert [a.assessment_id for a in report.assessments] == [a.id for a in found.upcoming]
    seen: set[UUID] = set()
    for entry in report.assessments:
        n = entry.numbers
        for topic in entry.topics:
            # Each in-scope topic appears once, under the assessment it's planned for.
            assert topic.topic_id not in seen
            seen.add(topic.topic_id)
            assert found.topics[topic.topic_id][0].id == entry.assessment_id
            assert topic.required_minutes == required_minutes(
                topics_by_id[topic.topic_id], request.studied_minutes.get(topic.topic_id, 0)
            )
            assert topic.planned_minutes == sum(
                b.minutes for b in result.blocks if b.topic_id == topic.topic_id
            )
            # Planned + short = required whenever something is short.
            assert topic.short_minutes >= 0
            if topic.short_minutes > 0:
                assert topic.planned_minutes + topic.short_minutes == topic.required_minutes
                event("a topic is short")
            # The planner's not_enough_time shortfall says the same.
            shortfalls = [
                s
                for s in entry.shortfalls
                if s.kind == "not_enough_time" and s.topic_id == topic.topic_id
            ]
            assert bool(shortfalls) == (topic.short_minutes > 0)
            for s in shortfalls:
                assert (s.required_minutes, s.scheduled_minutes) == (
                    topic.required_minutes,
                    topic.planned_minutes,
                )
        # Totals are the sums of their parts.
        assert n.required_minutes == sum(t.required_minutes for t in entry.topics)
        assert n.planned_minutes == sum(t.planned_minutes for t in entry.topics)
        assert n.short_minutes == sum(t.short_minutes for t in entry.topics)
        assert n.review_minutes == sum(
            b.minutes
            for b in result.blocks
            if b.topic_id is None and b.assessment_id == entry.assessment_id
        )
        assert n.booked_minutes == sum(b.minutes for b in result.blocks if b.start < entry.due_at)
        assert n.free_minutes == free_minutes(request, entry.due_at)
        # The status agrees with the numbers.
        assert n.status == status(n.short_minutes, n.free_minutes, n.booked_minutes)
        event(f"status {n.status}")
        # "Planned with" only for an assessment with topics but none of its own.
        if entry.planned_with:
            assert not entry.topics and found.covered[entry.assessment_id]
            assert entry.assessment_id not in entry.planned_with
        assert not (entry.planned_with and entry.all_done)
    assert seen == set(found.topics)

    overall = report.overall
    for name in ("required_minutes", "planned_minutes", "short_minutes", "review_minutes"):
        assert getattr(overall, name) == sum(getattr(a.numbers, name) for a in report.assessments)
    assert overall.booked_minutes == sum(b.minutes for b in result.blocks)
    assert overall.status == status(
        overall.short_minutes, overall.free_minutes, overall.booked_minutes
    )
    # Free time only grows with a later deadline.
    frees = [a.numbers.free_minutes for a in sorted(report.assessments, key=lambda a: a.due_at)]
    assert frees == sorted(frees)
    if report.last_deadline is not None:
        assert overall.free_minutes == free_minutes(request, report.last_deadline)
    # Levers only when something is short or tight.
    statuses = {overall.status, *(a.numbers.status for a in report.assessments)}
    assert bool(report.levers) == (statuses != {"fits"})
    narrowed = {lever.assessment_id for lever in report.levers if lever.kind == "narrow_topics"}
    assert narrowed <= {a.assessment_id for a in report.assessments if a.numbers.status == "short"}


@given(st.integers(0, 600), st.integers(0, 2000), st.integers(0, 2000))
def test_the_status_rule(short: int, free: int, booked: int) -> None:
    found = status(short, free, booked)
    if short > 0:
        assert found == "short"
    elif free == 0:
        # No free time: anything booked leaves nothing to spare.
        assert found == ("tight" if booked > 0 else "fits")
    else:
        spare = (free - booked) / free
        assert found == ("tight" if spare < TIGHT_PERCENT / 100 else "fits")


# --- worked examples -------------------------------------------------------------------

SAST = ZoneInfo("Africa/Johannesburg")
NOW = datetime(2026, 11, 23, 6, 0, tzinfo=UTC)  # Monday 08:00 SAST
MODULE = UUID(int=100)


def evenings(days: int, hours: int = 3) -> tuple[Interval, ...]:
    """18:00 local for ``hours`` on each of the next ``days`` days."""
    first = NOW.astimezone(SAST).replace(hour=18, minute=0)
    return tuple(
        Interval(first + timedelta(days=d), first + timedelta(days=d, hours=hours))
        for d in range(days)
    )


def request_with(workload: int, days: int, cap: int = 180) -> PlanInput:
    topic = TopicInput(UUID(int=1), MODULE, workload, 3)
    test = AssessmentInput(UUID(int=2), MODULE, NOW + timedelta(days=days), 30.0, (topic.id,))
    return PlanInput(NOW, evenings(days), cap, SAST, (test,), (topic,))


def test_a_roomy_plan_fits() -> None:
    report = feasibility(plan(request_with(100, 10)), request_with(100, 10))
    entry = report.assessments[0]
    assert entry.numbers.status == "fits"
    assert entry.numbers.free_minutes == 10 * 180
    assert report.levers == ()


def test_more_work_than_time_is_short_with_levers() -> None:
    request = request_with(900, 3, cap=60)
    report = feasibility(plan(request), request)
    entry = report.assessments[0]
    assert entry.numbers.status == "short"
    assert entry.numbers.short_minutes == 900 - entry.numbers.planned_minutes
    assert entry.numbers.free_minutes == 3 * 60
    # The cap (1 h) cuts each 3-hour evening, so raising it is offered.
    assert [lever.kind for lever in report.levers] == ["add_time", "raise_cap", "narrow_topics"]


def test_covered_with_little_to_spare_is_tight() -> None:
    # Two evenings, capped at 55 min: a 50-minute block each day (a study block and the
    # review) covers the topic's 50 minutes but leaves 10 of 110 free minutes (9 %).
    request = request_with(50, 2, cap=55)
    report = feasibility(plan(request), request)
    n = report.assessments[0].numbers
    assert (n.short_minutes, n.free_minutes, n.booked_minutes) == (0, 110, 100)
    assert n.status == "tight"
    assert [lever.kind for lever in report.levers] == ["add_time", "raise_cap"]


def test_free_minutes_split_at_local_midnight_and_cap_each_day() -> None:
    # 22:00 to 02:00 local is 2 h on each of two days; with a 90-minute cap, 3 h in all.
    start = datetime(2026, 11, 23, 22, 0, tzinfo=SAST)
    request = PlanInput(NOW, (Interval(start, start + timedelta(hours=4)),), 90, SAST, (), ())
    assert free_minutes(request, start + timedelta(days=1)) == 180
    assert free_minutes(request, start + timedelta(days=1), capped=False) == 240
    # Only from now: nothing before NOW counts, and nothing after ``until``.
    assert free_minutes(request, start + timedelta(hours=1)) == 60


def test_an_assessment_whose_topics_are_planned_for_a_sooner_one() -> None:
    topic = TopicInput(UUID(int=1), MODULE, 200, 3)
    test = AssessmentInput(UUID(int=2), MODULE, NOW + timedelta(days=4), None, (topic.id,), "test")
    task = AssessmentInput(
        UUID(int=3), MODULE, NOW + timedelta(days=8), None, (topic.id,), "assignment"
    )
    request = PlanInput(NOW, evenings(8), 180, SAST, (test, task), (topic,))
    result = plan(request)
    report = feasibility(result, request)

    later = report.assessments[1]
    assert later.assessment_id == task.id
    assert later.planned_with == (test.id,)
    assert later.topics == ()
    # The assignment gets no review; the test does.
    assert {b.assessment_id for b in result.blocks if b.kind == "review"} == {test.id}
