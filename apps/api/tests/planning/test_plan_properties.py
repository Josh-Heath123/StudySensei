"""Property tests for ``plan()`` (decision 0017), with random free time, caps, assessments and
topics. The properties themselves are in ``plan_checks.py``."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from random import Random
from uuid import UUID
from zoneinfo import ZoneInfo

from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st

from app.services.planning.availability import Interval, Rule, Window, expand
from app.services.planning.planner import AssessmentInput, PlanInput, TopicInput, plan
from tests.planning.plan_checks import check_plan, driving, spacing_applies

TIMEZONES = [
    "UTC",
    "Africa/Johannesburg",
    "Europe/London",  # clocks go forward on 29 March 2026, inside the range below
    "America/New_York",
    "Asia/Kolkata",  # +05:30
    "Asia/Kathmandu",  # +05:45
]
# Mostly reviewed kinds, so the review property is still exercised.
KINDS = ["exam", "exam", "test", "quiz", "assignment", "project", "other"]
# A few days before Europe/London's spring change.
BASE = datetime(2026, 3, 24, tzinfo=UTC)

PROPERTY_SETTINGS = settings(
    max_examples=300,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)


@st.composite
def raw_intervals(draw: st.DrawFn, horizon_days: int) -> tuple[Interval, ...]:
    """Any free intervals, in UTC: they may overlap, touch or cross local midnight."""
    out = []
    for _ in range(draw(st.integers(0, 30))):
        start = BASE + timedelta(minutes=draw(st.integers(0, (horizon_days + 2) * 1440)))
        out.append(Interval(start, start + timedelta(minutes=draw(st.integers(1, 400)))))
    return tuple(out)


@st.composite
def weekly_intervals(draw: st.DrawFn, tz: ZoneInfo, horizon_days: int) -> tuple[Interval, ...]:
    """Free time the way the app makes it: weekly windows expanded with ``expand()``."""
    rules = []
    for weekday in range(7):
        start = draw(st.integers(0, 1380))
        windows = draw(st.integers(0, 2))
        for _ in range(windows):
            end = min(1440, start + draw(st.integers(5, 300)))
            if end > start:
                rules.append(Rule(weekday, Window(start, end)))
            start = end + draw(st.integers(0, 120))
            if start >= 1440:
                break
    first = BASE.astimezone(tz).date() - timedelta(days=1)
    days = expand(rules, {}, first, first + timedelta(days=horizon_days + 3), tz, 1440)
    return tuple(i for day in days for i in day.intervals)


@st.composite
def roomy_intervals(draw: st.DrawFn, tz: ZoneInfo, horizon_days: int) -> tuple[Interval, ...]:
    """A student with time most days: one or two windows of 1-5 hours on every weekday, so
    the spacing and review properties are exercised, not just vacuously true."""
    rules = []
    for weekday in range(7):
        start = draw(st.integers(6 * 60, 12 * 60))
        for _ in range(draw(st.integers(1, 2))):
            end = min(1440, start + draw(st.integers(60, 300)))
            rules.append(Rule(weekday, Window(start, end)))
            start = end + draw(st.integers(30, 180))
            if start >= 1380:
                break
    first = BASE.astimezone(tz).date() - timedelta(days=1)
    days = expand(rules, {}, first, first + timedelta(days=horizon_days + 3), tz, 1440)
    return tuple(i for day in days for i in day.intervals)


@st.composite
def plan_inputs(draw: st.DrawFn, roomy: bool = False, mastery: bool = False) -> PlanInput:
    """``mastery``: also give each topic a random estimated mastery, or none (ADR 0031)."""
    tz = ZoneInfo(draw(st.sampled_from(TIMEZONES)))
    horizon_days = draw(st.integers(4 if roomy else 1, 21))
    now = BASE + timedelta(minutes=draw(st.integers(0, 2 * 1440)), seconds=draw(st.integers(0, 59)))
    if roomy:
        free = draw(roomy_intervals(tz, horizon_days))
    elif draw(st.booleans()):
        free = draw(weekly_intervals(tz, horizon_days))
    else:
        free = draw(raw_intervals(horizon_days))

    modules = [UUID(int=9000 + i) for i in range(draw(st.integers(1, 2)))]
    topics = tuple(
        TopicInput(
            id=UUID(int=1 + i),
            module_id=draw(st.sampled_from(modules)),
            workload_minutes=draw(st.none() | st.integers(0, 600)),
            confidence=draw(st.none() | st.integers(1, 5)),
            order=draw(st.integers(0, 20)),
            mastery=draw(st.none() | st.floats(0, 1)) if mastery else None,
        )
        for i in range(draw(st.integers(1, 5 if roomy else 8)))
    )
    studied = {t.id: draw(st.integers(0, 300)) for t in topics if draw(st.integers(0, 3)) == 0}
    assessments = []
    for i in range(draw(st.integers(1, 3 if roomy else 4))):
        module = draw(st.sampled_from(modules))
        in_module = [t.id for t in topics if t.module_id == module]
        earliest_due = 2 * 1440 if roomy else -1440
        due = now + timedelta(minutes=draw(st.integers(earliest_due, horizon_days * 1440)))
        weight = draw(st.none() | st.integers(0, 100).map(float))
        topic_ids = (
            draw(st.lists(st.sampled_from(in_module), unique=True, min_size=1 if roomy else 0))
            if in_module
            else []
        )
        kind = draw(st.sampled_from(KINDS))
        assessments.append(
            AssessmentInput(UUID(int=1000 + i), module, due, weight, tuple(topic_ids), kind)
        )
    request = PlanInput(
        now=now,
        free=free,
        daily_cap_minutes=draw(st.integers(100, 600) if roomy else st.integers(15, 600)),
        timezone=tz,
        assessments=tuple(assessments),
        topics=topics,
        studied_minutes=studied,
    )
    return draw(with_fixed(request))


@st.composite
def with_fixed(draw: st.DrawFn, request: PlanInput) -> PlanInput:
    """Often, the input re-planned (decision 0021): some of its own plan's blocks in the next
    24 h kept as fixed, and minutes already studied today."""
    if not draw(st.booleans()):
        return request
    soon = [b for b in plan(request).blocks if b.start < request.now + timedelta(hours=24)]
    fixed = tuple(b for b in soon if draw(st.booleans()))
    today = request.now.astimezone(request.timezone).date()
    studied_on = {today: draw(st.integers(0, request.daily_cap_minutes))}
    return replace(request, fixed=fixed, studied_on=studied_on)


@PROPERTY_SETTINGS
@given(st.one_of(plan_inputs(), plan_inputs(roomy=True)))
def test_every_plan_keeps_every_property(request: PlanInput) -> None:
    """No overlaps; inside free time; the daily cap; nothing in the past or after its
    deadline; two days per topic when time allows; final reviews; shortfalls."""
    result = plan(request)
    check_plan(request, result)
    # How often the conditional properties were really exercised (shown with
    # --hypothesis-show-statistics).
    if any(spacing_applies(request, result, a) for a in driving(request).values()):
        event("spacing applies")
    if any(b.kind == "review" for b in result.blocks):
        event("has a review")
    if result.shortfalls:
        event("has shortfalls")
    if request.fixed:
        event("has fixed blocks")


@PROPERTY_SETTINGS
@given(st.one_of(plan_inputs(), plan_inputs(roomy=True)), st.randoms(use_true_random=False))
def test_the_same_input_gives_the_same_plan_in_any_order(request: PlanInput, rng: Random) -> None:
    first = plan(request)
    assert plan(request) == first

    def shuffled[T](items: tuple[T, ...]) -> tuple[T, ...]:
        out = list(items)
        rng.shuffle(out)
        return tuple(out)

    reordered = PlanInput(
        now=request.now,
        free=shuffled(request.free),
        daily_cap_minutes=request.daily_cap_minutes,
        timezone=request.timezone,
        assessments=tuple(
            AssessmentInput(a.id, a.module_id, a.due_at, a.weight, shuffled(a.topic_ids), a.kind)
            for a in shuffled(request.assessments)
        ),
        topics=shuffled(request.topics),
        studied_minutes=dict(reversed(list(request.studied_minutes.items()))),
        fixed=shuffled(request.fixed),
        studied_on=dict(request.studied_on),
    )
    assert plan(reordered) == first


WITH_MASTERY = st.one_of(plan_inputs(mastery=True), plan_inputs(roomy=True, mastery=True))


@PROPERTY_SETTINGS
@given(WITH_MASTERY)
def test_every_property_holds_with_mastery(request: PlanInput) -> None:
    """ADR 0031: random estimated mastery changes time and order, never the properties."""
    result = plan(request)
    check_plan(request, result)
    # low_mastery only for mastery below 0.5; low_confidence only where there's no mastery.
    by_id = {t.id: t for t in request.topics}
    for block in result.blocks:
        found = by_id.get(block.topic_id) if block.topic_id else None
        if block.reason == "low_mastery":
            assert found is not None and found.mastery is not None and found.mastery < 0.5
        if block.reason == "low_confidence" and block not in request.fixed:
            assert found is not None and found.mastery is None
    if any(t.mastery is not None for t in request.topics):
        event("has mastery")
    if any(b.reason == "low_mastery" for b in result.blocks):
        event("has a low_mastery block")


@PROPERTY_SETTINGS
@given(WITH_MASTERY, st.randoms(use_true_random=False))
def test_with_mastery_the_same_input_gives_the_same_plan_in_any_order(
    request: PlanInput, rng: Random
) -> None:
    first = plan(request)
    topics = list(request.topics)
    rng.shuffle(topics)
    assessments = list(request.assessments)
    rng.shuffle(assessments)
    assert plan(replace(request, topics=tuple(topics), assessments=tuple(assessments))) == first


def test_dates_in_the_strategy_cover_a_dst_change() -> None:
    # Guard for BASE: Europe/London's spring change is within the generated range.
    london = ZoneInfo("Europe/London")
    assert BASE.astimezone(london).date() < date(2026, 3, 29)
    assert (BASE + timedelta(days=21)).astimezone(london).date() > date(2026, 3, 29)
