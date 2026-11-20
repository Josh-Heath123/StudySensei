"""The planner's properties (decision 0017), checked against a plan and the input it came from.

Each check is written from the rules, not from the planner's code, so the property tests and
the scenario test share one definition of "a valid plan". The planner's grid is 5 minutes:
free time is rounded inward to it, and blocks are 50 or 25 minutes with a 10-minute break
between neighbours.
"""

import math
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta
from itertools import pairwise
from uuid import UUID

from app.services.planning.planner import (
    BLOCK_MINUTES,
    BREAK_MINUTES,
    MIN_BLOCKS,
    REVIEW_DAYS,
    SHORT_BLOCK_MINUTES,
    AssessmentInput,
    Block,
    Plan,
    PlanInput,
    required_minutes,
)

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

Span = tuple[int, int]  # minutes since the epoch, end exclusive


def minute(at: datetime) -> float:
    return (at - EPOCH).total_seconds() / 60


def ceil5(at: datetime) -> int:
    return math.ceil(minute(at) / 5) * 5


def floor5(at: datetime) -> int:
    return math.floor(minute(at) / 5) * 5


def merged(spans: Iterable[Span]) -> list[Span]:
    out: list[Span] = []
    for start, end in sorted(spans):
        if end <= start:
            continue
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


def free_spans(request: PlanInput) -> list[Span]:
    """The free intervals, merged, in whole minutes (not yet on the grid)."""
    return merged((math.ceil(minute(i.start)), math.floor(minute(i.end))) for i in request.free)


def local_day(at: datetime, request: PlanInput) -> date:
    return at.astimezone(request.timezone).date()


def day_span(day: date, request: PlanInput) -> Span:
    """Local midnight to the next one, in minutes since the epoch."""
    tz = request.timezone
    start = datetime.combine(day, time(), tzinfo=tz).astimezone(UTC)
    end = datetime.combine(day + timedelta(days=1), time(), tzinfo=tz).astimezone(UTC)
    return int(minute(start)), int(minute(end))


def gaps(request: PlanInput, lo: int, hi: int, busy: Iterable[Block]) -> list[Span]:
    """Free time within [lo, hi) on the 5-minute grid, minus each busy block and its break."""
    taken = merged(
        (int(minute(b.start)) - BREAK_MINUTES, int(minute(b.end)) + BREAK_MINUTES) for b in busy
    )
    out: list[Span] = []
    for start, end in free_spans(request):
        start = max(math.ceil(start / 5) * 5, lo)
        end = min(math.floor(end / 5) * 5, hi)
        pieces = [(start, end)]
        for t_start, t_end in taken:
            cut: list[Span] = []
            for p_start, p_end in pieces:
                if t_end <= p_start or t_start >= p_end:
                    cut.append((p_start, p_end))
                    continue
                cut.append((p_start, t_start))
                cut.append((t_end, p_end))
            pieces = cut
        out.extend((s, e) for s, e in pieces if e > s)
    return out


def upcoming(request: PlanInput) -> list[AssessmentInput]:
    return [a for a in request.assessments if a.due_at > request.now]


def known_topics(request: PlanInput, assessment: AssessmentInput) -> set[UUID]:
    in_module = {t.id for t in request.topics if t.module_id == assessment.module_id}
    return set(assessment.topic_ids) & in_module


def assessment_key(a: AssessmentInput) -> tuple[datetime, float, str]:
    return (a.due_at, -(a.weight or 0), str(a.id))


def driving(request: PlanInput) -> dict[UUID, AssessmentInput]:
    """Each topic with work left → the soonest upcoming assessment that covers it."""
    topics = {t.id: t for t in request.topics}
    out: dict[UUID, AssessmentInput] = {}
    for a in sorted(upcoming(request), key=assessment_key):
        for topic_id in known_topics(request, a):
            topic = topics[topic_id]
            studied = request.studied_minutes.get(topic_id, 0)
            if topic_id not in out and required_minutes(topic, studied) > 0:
                out[topic_id] = a
    return out


# --- the checks ------------------------------------------------------------------------


def check_plan(request: PlanInput, result: Plan) -> None:
    check_blocks_are_valid(request, result)
    check_daily_cap(request, result)
    check_spacing(request, result)
    check_final_reviews(request, result)
    check_shortfalls(request, result)


def check_blocks_are_valid(request: PlanInput, result: Plan) -> None:
    """Sorted, no overlaps (and a break between neighbours), inside free time, on the grid,
    not in the past, not after the deadline, within one local day."""
    by_id = {a.id: a for a in request.assessments}
    spans = free_spans(request)
    blocks = result.blocks
    assert list(blocks) == sorted(blocks, key=lambda b: (b.start, b.end))
    for before, after in pairwise(blocks):
        assert after.start >= before.end + timedelta(minutes=BREAK_MINUTES), (before, after)
    for block in blocks:
        start, end = minute(block.start), minute(block.end)
        assert block.minutes in (BLOCK_MINUTES, SHORT_BLOCK_MINUTES), block
        assert start % 5 == 0, block
        assert any(s <= start and end <= e for s, e in spans), f"outside free time: {block}"
        assert block.start >= request.now, f"in the past: {block}"
        assessment = by_id[block.assessment_id]
        assert block.end <= assessment.due_at, f"after its deadline: {block}"
        assert block.module_id == assessment.module_id
        _, day_end = day_span(local_day(block.start, request), request)
        assert end <= day_end, f"crosses local midnight: {block}"
        if block.kind == "review":
            assert block.topic_id is None and block.reason == "final_review"
        else:
            assert block.topic_id in known_topics(request, assessment), block


def check_daily_cap(request: PlanInput, result: Plan) -> None:
    per_day: dict[date, int] = defaultdict(int)
    for block in result.blocks:
        per_day[local_day(block.start, request)] += block.minutes
    for day, total in per_day.items():
        assert total <= request.daily_cap_minutes, (day, total)


def _fits_50s(spans: list[Span]) -> int:
    """How many 50-minute blocks, with breaks, pack into these spans."""
    return sum(
        (end - start + BREAK_MINUTES) // (BLOCK_MINUTES + BREAK_MINUTES) for start, end in spans
    )


def spacing_applies(request: PlanInput, result: Plan, assessment: AssessmentInput) -> bool:
    """Whether the free time before ``assessment`` is enough for every in-scope topic's two
    minimum blocks on two days. Only whole local days between today and the deadline's day
    count, after the final reviews. A day can give each topic at most one of its two blocks,
    so the test (Hall's condition) is: the sum over those days of min(50-minute blocks that
    fit, topics due by then) is at least twice the number of those topics.
    """
    drivers = driving(request)
    in_scope = [t for t, a in drivers.items() if a.due_at <= assessment.due_at]
    if not in_scope:
        return False
    reviews = [b for b in result.blocks if b.kind == "review"]
    today = local_day(request.now, request)
    last = local_day(assessment.due_at, request)
    total = 0
    day = today + timedelta(days=1)
    while day < last:
        lo, hi = day_span(day, request)
        on_day = [r for r in reviews if local_day(r.start, request) == day]
        room = request.daily_cap_minutes - sum(r.minutes for r in on_day)
        fits = min(_fits_50s(gaps(request, lo, hi, reviews)), room // BLOCK_MINUTES)
        total += min(fits, len(in_scope))
        day += timedelta(days=1)
    return total >= MIN_BLOCKS * len(in_scope)


def check_spacing(request: PlanInput, result: Plan) -> None:
    """When time allows, each in-scope topic has blocks on at least two local days."""
    drivers = driving(request)
    for assessment in upcoming(request):
        if not spacing_applies(request, result, assessment):
            continue
        for topic_id, driver in drivers.items():
            if driver.id != assessment.id:
                continue
            days = {
                local_day(b.start, request)
                for b in result.blocks
                if b.topic_id == topic_id and b.kind == "study"
            }
            assert len(days) >= MIN_BLOCKS, f"topic {topic_id} on {len(days)} day(s)"


def review_spot_exists(request: PlanInput, result: Plan, assessment: AssessmentInput) -> bool:
    """Whether the 3 days before ``assessment`` have room for a review, around the other
    reviews (which are placed before any study block)."""
    lo = max(ceil5(request.now), ceil5(assessment.due_at - timedelta(days=REVIEW_DAYS)))
    hi = floor5(assessment.due_at)
    others = [b for b in result.blocks if b.kind == "review" and b.assessment_id != assessment.id]
    day = local_day(request.now, request)
    while True:
        day_lo, day_hi = day_span(day, request)
        if day_lo >= hi:
            return False
        room = request.daily_cap_minutes - sum(
            r.minutes for r in others if local_day(r.start, request) == day
        )
        for start, end in gaps(request, max(lo, day_lo), min(hi, day_hi), others):
            length = BLOCK_MINUTES if end - start >= BLOCK_MINUTES else SHORT_BLOCK_MINUTES
            if end - start >= length and room >= length:
                return True
        day += timedelta(days=1)


def check_final_reviews(request: PlanInput, result: Plan) -> None:
    """One review per assessment with topics, in its last 3 days, whenever there's room."""
    for assessment in upcoming(request):
        reviews = [
            b for b in result.blocks if b.kind == "review" and b.assessment_id == assessment.id
        ]
        assert len(reviews) <= 1
        if not known_topics(request, assessment):
            assert not reviews
            continue
        if reviews:
            review = reviews[0]
            assert review.start >= assessment.due_at - timedelta(days=REVIEW_DAYS), review
            continue
        assert not review_spot_exists(request, result, assessment), (
            f"no review for {assessment.id}, but there was room"
        )
        assert any(
            s.kind == "no_review_time" and s.assessment_id == assessment.id
            for s in result.shortfalls
        )


def check_shortfalls(request: PlanInput, result: Plan) -> None:
    """A shortfall whenever a topic needs more minutes than it got (and none otherwise), and
    one for every topic with no estimate."""
    topics = {t.id: t for t in request.topics}
    scheduled: dict[UUID, int] = defaultdict(int)
    for block in result.blocks:
        if block.topic_id is not None:
            scheduled[block.topic_id] += block.minutes
    short = {(s.topic_id, s.kind): s for s in result.shortfalls if s.topic_id is not None}
    for topic_id, assessment in driving(request).items():
        topic = topics[topic_id]
        need = required_minutes(topic, request.studied_minutes.get(topic_id, 0))
        got = scheduled[topic_id]
        found = short.get((topic_id, "not_enough_time"))
        if got < need:
            assert found is not None, f"topic {topic_id}: {got} of {need} min, no shortfall"
            assert (found.required_minutes, found.scheduled_minutes) == (need, got)
            assert found.assessment_id == assessment.id
        else:
            assert found is None, f"topic {topic_id}: a shortfall with {got} of {need} min"
        if topic.workload_minutes is None:
            assert (topic_id, "no_estimate") in short
