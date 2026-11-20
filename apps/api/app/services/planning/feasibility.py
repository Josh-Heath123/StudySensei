"""Feasibility: does the plan cover what each assessment needs? (decision 0018)

Pure: a function of the ``Plan`` and the ``PlanInput`` it came from. Numbers only; the words
are in ``explain.py``.

- **Per topic:** required minutes (``planner.required_minutes``), planned minutes (its study
  blocks) and short = ``max(0, required - planned)``. Overplanning one topic never covers
  another.
- **Per assessment:** the sums over the topics planned for it, its review minutes, the free
  minutes from now to its deadline (each local day at most the daily cap), and the minutes
  booked by every block (any assessment's) that starts before the deadline.
- **Status:** ``short`` when anything is short; ``tight`` when it's covered but the free time
  left over (free - booked) is under 15 % of the free time; otherwise ``fits``.
"""

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from app.services.planning.availability import MINUTES_PER_DAY, local_to_utc
from app.services.planning.planner import AssessmentInput, Plan, PlanInput, Shortfall, scope

TIGHT_PERCENT = 15

Status = Literal["fits", "tight", "short"]
LeverKind = Literal["add_time", "raise_cap", "narrow_topics"]


@dataclass(frozen=True)
class TopicFeasibility:
    topic_id: UUID
    required_minutes: int
    planned_minutes: int
    short_minutes: int


@dataclass(frozen=True)
class Numbers:
    required_minutes: int
    planned_minutes: int
    short_minutes: int
    review_minutes: int
    free_minutes: int
    booked_minutes: int
    status: Status


@dataclass(frozen=True)
class AssessmentFeasibility:
    assessment_id: UUID
    due_at: datetime
    numbers: Numbers
    topics: tuple[TopicFeasibility, ...]
    shortfalls: tuple[Shortfall, ...]
    # When it covers topics but none is planned for it: the sooner assessments they're
    # planned for (decision 0019), in deadline order. Empty otherwise.
    planned_with: tuple[UUID, ...] = ()
    # It covers topics, but none needs more time (measured study covers them).
    all_done: bool = False


@dataclass(frozen=True)
class Lever:
    kind: LeverKind
    # For narrow_topics: the assessment to narrow.
    assessment_id: UUID | None = None


@dataclass(frozen=True)
class Feasibility:
    assessments: tuple[AssessmentFeasibility, ...]
    # Over every planned assessment, up to the last deadline (None with nothing to plan).
    overall: Numbers
    last_deadline: datetime | None
    levers: tuple[Lever, ...]


def status(short: int, free: int, booked: int) -> Status:
    """``short`` if anything is short; ``tight`` if the time left over is under 15 % of the
    free time; else ``fits``."""
    if short > 0:
        return "short"
    if (free - booked) * 100 < TIGHT_PERCENT * free:
        return "tight"
    return "fits"


def free_minutes(request: PlanInput, until: datetime, *, capped: bool = True) -> int:
    """Free minutes from now to ``until``: merged free time, split at local midnight, each
    local day at most the daily cap (unless ``capped`` is False), floored to whole minutes
    per day."""
    spans: list[tuple[datetime, datetime]] = []
    for interval in sorted(request.free, key=lambda i: (i.start, i.end)):
        start, end = max(interval.start, request.now), min(interval.end, until)
        if end <= start:
            continue
        if spans and start <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], end))
        else:
            spans.append((start, end))
    if not spans:
        return 0
    tz = request.timezone
    per_day: dict[object, float] = defaultdict(float)
    day = spans[0][0].astimezone(tz).date()
    last = spans[-1][1].astimezone(tz).date()
    while day <= last:
        day_start, day_end = local_to_utc(day, 0, tz), local_to_utc(day, MINUTES_PER_DAY, tz)
        for start, end in spans:
            overlap = (min(end, day_end) - max(start, day_start)).total_seconds()
            if overlap > 0:
                per_day[day] += overlap / 60
        day += timedelta(days=1)
    cap = request.daily_cap_minutes if capped else MINUTES_PER_DAY
    return sum(min(math.floor(m), cap) for m in per_day.values())


def _due_order(assessment: AssessmentInput) -> tuple[datetime, str]:
    return (assessment.due_at, str(assessment.id))


def feasibility(result: Plan, request: PlanInput) -> Feasibility:
    found = scope(request)
    planned: dict[UUID, int] = defaultdict(int)
    reviews: dict[UUID, int] = defaultdict(int)
    for block in result.blocks:
        if block.topic_id is None:
            reviews[block.assessment_id] += block.minutes
        else:
            planned[block.topic_id] += block.minutes

    assessments: list[AssessmentFeasibility] = []
    for assessment in found.upcoming:
        topics = tuple(
            TopicFeasibility(
                topic_id,
                need,
                planned[topic_id],
                max(0, need - planned[topic_id]),
            )
            for topic_id, (planned_for, need) in sorted(
                found.topics.items(), key=lambda item: str(item[0])
            )
            if planned_for.id == assessment.id
        )
        free = free_minutes(request, assessment.due_at)
        booked = sum(b.minutes for b in result.blocks if b.start < assessment.due_at)
        short = sum(t.short_minutes for t in topics)
        numbers = Numbers(
            required_minutes=sum(t.required_minutes for t in topics),
            planned_minutes=sum(t.planned_minutes for t in topics),
            short_minutes=short,
            review_minutes=reviews[assessment.id],
            free_minutes=free,
            booked_minutes=booked,
            status=status(short, free, booked),
        )
        shortfalls = tuple(s for s in result.shortfalls if s.assessment_id == assessment.id)
        covered = found.covered[assessment.id]
        elsewhere = [found.topics[t][0] for t in covered if t in found.topics]
        planned_with = (
            tuple(dict.fromkeys(a.id for a in sorted(elsewhere, key=_due_order)))
            if covered and not topics
            else ()
        )
        assessments.append(
            AssessmentFeasibility(
                assessment.id,
                assessment.due_at,
                numbers,
                topics,
                shortfalls,
                planned_with,
                all_done=bool(covered) and not topics and not planned_with,
            )
        )

    last = max((a.due_at for a in found.upcoming), default=None)
    free = free_minutes(request, last) if last is not None else 0
    booked = sum(b.minutes for b in result.blocks)
    short = sum(a.numbers.short_minutes for a in assessments)
    overall = Numbers(
        required_minutes=sum(a.numbers.required_minutes for a in assessments),
        planned_minutes=sum(a.numbers.planned_minutes for a in assessments),
        short_minutes=short,
        review_minutes=sum(a.numbers.review_minutes for a in assessments),
        free_minutes=free,
        booked_minutes=booked,
        status=status(short, free, booked),
    )
    cap_binds = last is not None and free_minutes(request, last, capped=False) > free
    return Feasibility(
        tuple(assessments), overall, last, levers(assessments, overall, cap_binds=cap_binds)
    )


def levers(
    assessments: list[AssessmentFeasibility], overall: Numbers, *, cap_binds: bool
) -> tuple[Lever, ...]:
    """What the student can change when something is short or tight: more study time, a
    higher daily cap (only when the cap cuts some day's free time), or fewer topics in each
    short assessment."""
    if overall.status == "fits" and all(a.numbers.status == "fits" for a in assessments):
        return ()
    narrow = tuple(
        Lever("narrow_topics", a.assessment_id)
        for a in assessments
        if a.numbers.status == "short" and a.topics
    )
    cap = (Lever("raise_cap"),) if cap_binds else ()
    return (Lever("add_time"), *cap, *narrow)
