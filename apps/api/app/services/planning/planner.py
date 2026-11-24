"""Planner v1: what to study, when. A pure function of its inputs (decisions 0017, 0019-0021,
0031).

No database, no clock, no AI: ``plan()`` takes a ``PlanInput`` and returns the same ``Plan``
for the same input, whatever order its lists come in. It works in three passes, sooner
deadlines first:

1. **Final reviews:** one block in the 3 days before each exam, test or quiz, as late as fits
   (assignments, projects and "other" get none).
2. **Two spaced blocks per topic** on different local days, as early as fits. A later
   assessment's topics look first at the days after the previous deadline.
3. **The rest of each topic's workload,** one block per topic per round, preferring a day
   the topic doesn't have yet, then a spot that isn't next to its own block.

Times are on a 5-minute grid (free time is rounded inward to it). Blocks are 50 minutes, or
25 where a 50 doesn't fit, with the timer's 10-minute break between neighbours. Task 3 turns
the shortfalls into the feasibility report (``feasibility.py``) and the reasons into text
(``explain.py``); task 4 stores blocks.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from app.services.planning.availability import MINUTES_PER_DAY, Interval, local_to_utc

BLOCK_MINUTES = 50
SHORT_BLOCK_MINUTES = 25
BREAK_MINUTES = 10
MIN_BLOCKS = 2
REVIEW_DAYS = 3
URGENT_DAYS = 7
# Assessment kinds that get a final review (decision 0019).
REVIEW_KINDS = frozenset({"exam", "test", "quiz"})
# Starting confidence → percent of the remaining workload. Not rated counts as 3.
CONFIDENCE_PERCENT = {1: 150, 2: 125, 3: 100, 4: 85, 5: 70}
# Estimated mastery → percent (ADR 0031): 150 - mastery %, kept within these bounds.
MASTERY_PERCENT_MAX = 150
MASTERY_PERCENT_MIN = 70
# Below this a unit's first block is low_mastery and a first pass (the "weak" band's edge).
WEAK_BELOW = 0.5


@dataclass(frozen=True)
class AssessmentInput:
    id: UUID
    module_id: UUID
    due_at: datetime
    # 0-100, or None (sorts as 0).
    weight: float | None
    topic_ids: tuple[UUID, ...]
    # Only exams, tests and quizzes get a final review (decision 0019).
    kind: str = "exam"


@dataclass(frozen=True)
class TopicInput:
    id: UUID
    module_id: UUID
    # The student's figure, else the estimate (decision 0016), else None.
    workload_minutes: int | None
    # Self-rated 1-5, or None for not rated.
    confidence: int | None
    # Course order: the topic's index in its module's tree, pre-order (decision 0019).
    order: int = 0
    # Mastery 0-1 when its status is "estimated" (ADR 0031), else None: the rating is used.
    mastery: float | None = None


@dataclass(frozen=True)
class PlanInput:
    now: datetime
    # Free time in UTC (from ``availability.expand``).
    free: tuple[Interval, ...]
    daily_cap_minutes: int
    timezone: ZoneInfo
    assessments: tuple[AssessmentInput, ...]
    topics: tuple[TopicInput, ...]
    # Minutes already studied per topic, measured from the sessions.
    studied_minutes: Mapping[UUID, int] = field(default_factory=dict)
    # Blocks kept from the previous version (decision 0021): returned unchanged, and busy.
    fixed: tuple["Block", ...] = ()
    # Measured minutes already studied per local date; they count against that day's cap.
    studied_on: Mapping[date, int] = field(default_factory=dict)


BlockKind = Literal["study", "review"]
Reason = Literal[
    "final_review",  # the review in the days before an assessment
    "spacing",  # a topic's first block on a second day
    "no_estimate",  # a topic with no workload figure gets its two default blocks
    "low_confidence",  # the topic is rated 1 or 2 (and has no estimated mastery)
    "low_mastery",  # the topic's estimated mastery is below 0.5 (ADR 0031)
    "urgency",  # the assessment is due within 7 days of the block
    "workload",  # the rest of the topic's workload
]
ShortfallKind = Literal[
    "no_estimate",  # no workload figure: two blocks were planned as a default
    "not_enough_time",  # fewer minutes planned than the topic needs
    "not_spaced",  # fewer than two days with a block for the topic
    "no_review_time",  # no free time for the final review
    "no_topics",  # the assessment covers no topics, so nothing was planned for it
]


@dataclass(frozen=True)
class Block:
    start: datetime
    end: datetime
    module_id: UUID
    assessment_id: UUID
    # None for a review, which covers all of the assessment's topics.
    topic_id: UUID | None
    kind: BlockKind
    reason: Reason

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


@dataclass(frozen=True)
class Shortfall:
    kind: ShortfallKind
    assessment_id: UUID
    topic_id: UUID | None = None
    required_minutes: int = 0
    scheduled_minutes: int = 0


@dataclass(frozen=True)
class Plan:
    # Sorted by start.
    blocks: tuple[Block, ...]
    shortfalls: tuple[Shortfall, ...]


def mastery_percent(mastery: float) -> int:
    """Mastery as a whole percent, rounded half up: 0.344 → 34. The text shows this figure and
    ``strength_percent`` is computed from it, so the two always agree."""
    return math.floor(mastery * 100 + 0.5)


def mastery_time_percent(mastery: float) -> int:
    """``clamp(150 - mastery %, 70, 150)`` (ADR 0031): mastery 0 → 150, 0.5 → 100, 0.8 or
    more → 70."""
    raw = MASTERY_PERCENT_MAX - mastery_percent(mastery)
    return min(MASTERY_PERCENT_MAX, max(MASTERY_PERCENT_MIN, raw))


def strength_percent(topic: TopicInput) -> int:
    """The percent of its remaining workload a topic gets: from its estimated mastery when it
    has one (``mastery_time_percent``), else its confidence (``CONFIDENCE_PERCENT``; not rated
    counts as 3)."""
    if topic.mastery is not None:
        return mastery_time_percent(topic.mastery)
    return CONFIDENCE_PERCENT.get(topic.confidence or 3, 100)


def strength(topic: TopicInput) -> float:
    """How strong a topic is, 0-1, for priority (ADR 0031): its estimated mastery, else its
    rating mapped (c - 1) / 4, else 0.5. Without mastery this orders exactly as confidence."""
    if topic.mastery is not None:
        return topic.mastery
    if topic.confidence is not None:
        return (topic.confidence - 1) / 4
    return 0.5


def required_minutes(topic: TopicInput, studied: int) -> int:
    """What a topic still needs, rounded up to 5 minutes: ``max(0, workload - studied)``
    scaled by ``strength_percent``. A topic with no workload figure needs its two default
    blocks, less what's been studied."""
    if topic.workload_minutes is None:
        return max(0, MIN_BLOCKS * BLOCK_MINUTES - studied)
    remaining = max(0, topic.workload_minutes - studied)
    percent = strength_percent(topic)
    scaled = math.ceil(remaining * percent / 100)
    return math.ceil(scaled / 5) * 5


# --- internals: minutes since the epoch, on a 5-minute grid ------------------------------

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

Spot = tuple["_Day", int, int]  # (day, start, length)


def _minutes(at: datetime) -> float:
    return (at - _EPOCH).total_seconds() / 60


def _ceil5(value: float) -> int:
    return math.ceil(value / 5) * 5


def _floor5(value: float) -> int:
    return math.floor(value / 5) * 5


def _datetime(minute: int) -> datetime:
    return _EPOCH + timedelta(minutes=minute)


@dataclass
class _Placed:
    start: int
    end: int
    assessment: AssessmentInput
    topic_id: UUID | None
    kind: BlockKind
    reason: Reason
    # The fixed block this stands for, returned unchanged (decision 0021).
    fixed: "Block | None" = None


@dataclass
class _Day:
    date: date
    start: int
    end: int
    # Free time that day, on the grid, from now on.
    pieces: list[tuple[int, int]]
    used: int = 0
    # Sorted by start.
    blocks: list[_Placed] = field(default_factory=list)
    # The days either side: free time can run over midnight, and the break between a
    # block at 23:00 and one at 00:00 still counts.
    previous: "_Day | None" = field(default=None, repr=False)
    following: "_Day | None" = field(default=None, repr=False)

    def gaps(self, lo: int, hi: int) -> list[tuple[int, int]]:
        """Stretches within [lo, hi) that can take a block: the free pieces, minus each block
        and the break on either side of it (a neighbouring day's blocks included)."""
        nearby = (
            (self.previous.blocks[-1:] if self.previous else [])
            + self.blocks
            + (self.following.blocks[:1] if self.following else [])
        )
        out: list[tuple[int, int]] = []
        for piece_start, piece_end in self.pieces:
            cursor, end = max(piece_start, lo), min(piece_end, hi)
            for block in nearby:
                busy_start, busy_end = block.start - BREAK_MINUTES, block.end + BREAK_MINUTES
                if busy_end <= cursor:
                    continue
                if busy_start >= end:
                    break
                if busy_start - cursor >= SHORT_BLOCK_MINUTES:
                    out.append((cursor, busy_start))
                cursor = max(cursor, busy_end)
            if end - cursor >= SHORT_BLOCK_MINUTES:
                out.append((cursor, end))
        return out

    def length_for(self, gap: tuple[int, int], cap: int) -> int | None:
        """The block length for a gap (25 only where 50 doesn't fit), or None if the day's
        cap has no room for it."""
        length = BLOCK_MINUTES if gap[1] - gap[0] >= BLOCK_MINUTES else SHORT_BLOCK_MINUTES
        return length if self.used + length <= cap else None

    def next_to(self, start: int, end: int, topic_id: UUID) -> bool:
        """Whether a block on ``topic_id`` is directly next to [start, end): only the break
        lies between them (a neighbouring day's blocks included). Decision 0020."""
        nearby = (
            (self.previous.blocks[-1:] if self.previous else [])
            + self.blocks
            + (self.following.blocks[:1] if self.following else [])
        )
        return any(
            b.topic_id == topic_id
            and (b.end + BREAK_MINUTES == start or end + BREAK_MINUTES == b.start)
            for b in nearby
        )

    def count(self, topic_id: UUID) -> int:
        """How many of the day's blocks are on ``topic_id``."""
        return sum(1 for b in self.blocks if b.topic_id == topic_id)


@dataclass
class _Topic:
    input: TopicInput
    assessment: AssessmentInput
    required: int
    scheduled: int = 0
    days: set[date] = field(default_factory=set)


class _Calendar:
    """The local days from now to the last deadline, with their free time and blocks."""

    def __init__(self, request: PlanInput, start: int, end: int) -> None:
        self.cap = request.daily_cap_minutes
        self.start = start
        self.days = self._days(request, start, end)

    @staticmethod
    def _days(request: PlanInput, start: int, end: int) -> list[_Day]:
        tz = request.timezone
        spans: list[tuple[int, int]] = []
        for interval in sorted(request.free, key=lambda i: (i.start, i.end)):
            s, e = math.ceil(_minutes(interval.start)), math.floor(_minutes(interval.end))
            if spans and s <= spans[-1][1]:
                spans[-1] = (spans[-1][0], max(spans[-1][1], e))
            elif e > s:
                spans.append((s, e))
        days: list[_Day] = []
        day = _datetime(start).astimezone(tz).date()
        while (day_start := int(_minutes(local_to_utc(day, 0, tz)))) < end:
            day_end = int(_minutes(local_to_utc(day, MINUTES_PER_DAY, tz)))
            pieces = []
            for s, e in spans:
                s, e = _ceil5(max(s, day_start, start)), _floor5(min(e, day_end, end))
                if e - s >= SHORT_BLOCK_MINUTES:
                    pieces.append((s, e))
            days.append(_Day(day, day_start, day_end, pieces, request.studied_on.get(day, 0)))
            day += timedelta(days=1)
        for before, after in pairwise(days):
            before.following, after.previous = after, before
        return days

    def place(self, spot: Spot, block: _Placed) -> None:
        day, start, length = spot
        block.start, block.end = start, start + length
        day.blocks.append(block)
        day.blocks.sort(key=lambda b: b.start)
        day.used += length

    def latest(self, lo: int, hi: int) -> Spot | None:
        """The latest spot in [lo, hi)."""
        for day in reversed(self.days):
            if day.start >= hi or day.end <= lo:
                continue
            for gap in reversed(day.gaps(lo, hi)):
                length = day.length_for(gap, self.cap)
                if length is not None:
                    return day, gap[1] - length, length
        return None

    def earliest(self, hi: int, avoid: set[date], prefer_after: date | None) -> Spot | None:
        """The earliest spot before ``hi`` on a day not in ``avoid``, looking first at the
        days after ``prefer_after``."""
        for after in [prefer_after, None] if prefer_after is not None else [None]:
            for day in self.days:
                if day.start >= hi:
                    break
                if day.date in avoid or (after is not None and day.date <= after):
                    continue
                for gap in day.gaps(self.start, hi):
                    length = day.length_for(gap, self.cap)
                    if length is not None:
                        return day, gap[0], length
        return None

    def spread(self, topic: _Topic, hi: int) -> Spot | None:
        """An extra block before ``hi``: the earliest spot on a day without the topic. When
        every day with room already has it (decision 0020): the day with the fewest of its
        blocks, then a spot not directly next to its own block, then the earliest. Each gap
        is tried at its earliest and its latest start. With the topic on one day only (no
        other day has room), there's nothing to spread: the earliest spot, as before."""
        spreading = len(topic.days) >= MIN_BLOCKS
        best: tuple[int, int, int, Spot] | None = None
        for day in self.days:
            if day.start >= hi:
                break
            count = day.count(topic.input.id)
            for gap in day.gaps(self.start, hi):
                length = day.length_for(gap, self.cap)
                if length is None:
                    continue
                if day.date not in topic.days:
                    return day, gap[0], length
                starts = (gap[0], gap[1] - length) if spreading else (gap[0],)
                for start in dict.fromkeys(starts):
                    level = (
                        1 if spreading and day.next_to(start, start + length, topic.input.id) else 0
                    )
                    key = (count if spreading else 0, level, start)
                    if best is None or key < best[:3]:
                        best = (*key, (day, start, length))
        return None if best is None else best[3]


def _assessment_key(assessment: AssessmentInput) -> tuple[datetime, float, str]:
    """Sooner deadlines first, then higher weight, then the id (stable)."""
    return (assessment.due_at, -(assessment.weight or 0), str(assessment.id))


def _topic_key(topic: _Topic) -> tuple[float, int, str]:
    """Within an assessment: lower strength first (estimated mastery, else the rating), then
    course order, then the id."""
    return (strength(topic.input), topic.input.order, str(topic.input.id))


def _study_reason(topic: _Topic, start: int) -> Reason:
    if topic.input.workload_minutes is None:
        return "no_estimate"
    if topic.input.mastery is not None:
        if topic.input.mastery < WEAK_BELOW:
            return "low_mastery"
    elif (topic.input.confidence or 3) <= 2:
        return "low_confidence"
    if _minutes(topic.assessment.due_at) - start <= URGENT_DAYS * MINUTES_PER_DAY:
        return "urgency"
    return "workload"


@dataclass(frozen=True)
class Scope:
    """What ``plan()`` plans for: the upcoming assessments in priority order, each one's
    topics (known topics of its own module), and each in-scope topic with the assessment it's
    planned for (the soonest that covers it) and its required minutes."""

    upcoming: tuple[AssessmentInput, ...]
    covered: Mapping[UUID, tuple[UUID, ...]]
    topics: Mapping[UUID, tuple[AssessmentInput, int]]


def scope(request: PlanInput) -> Scope:
    upcoming = tuple(
        sorted((a for a in request.assessments if a.due_at > request.now), key=_assessment_key)
    )
    topics_by_id = {t.id: t for t in request.topics}
    covered = {
        a.id: tuple(
            sorted(
                {
                    i
                    for i in a.topic_ids
                    if i in topics_by_id and topics_by_id[i].module_id == a.module_id
                },
                key=str,
            )
        )
        for a in upcoming
    }
    # Each topic with work left is planned for the soonest assessment that covers it.
    topics: dict[UUID, tuple[AssessmentInput, int]] = {}
    for assessment in upcoming:
        for topic_id in covered[assessment.id]:
            need = required_minutes(
                topics_by_id[topic_id], request.studied_minutes.get(topic_id, 0)
            )
            if topic_id not in topics and need > 0:
                topics[topic_id] = (assessment, need)
    return Scope(upcoming, covered, topics)


def plan(request: PlanInput) -> Plan:
    """The plan for ``request`` (see the module docstring and decision 0017)."""
    start = _ceil5(_minutes(request.now))
    found = scope(request)
    upcoming = list(found.upcoming)
    fixed = tuple(sorted(set(request.fixed), key=lambda b: (b.start, b.end, str(b.topic_id))))
    if not upcoming:
        return Plan(fixed, ())
    topics_by_id = {t.id: t for t in request.topics}
    topics = {
        topic_id: _Topic(topics_by_id[topic_id], assessment, need)
        for topic_id, (assessment, need) in found.topics.items()
    }
    groups = [
        (a, sorted((t for t in topics.values() if t.assessment.id == a.id), key=_topic_key))
        for a in upcoming
    ]
    groups = [(a, group) for a, group in groups if group]

    calendar = _Calendar(request, start, _floor5(_minutes(upcoming[-1].due_at)))
    shortfalls: list[Shortfall] = []

    # 0. Fixed blocks (decision 0021): busy time on their local day, counted against its cap;
    #    a study block is time scheduled for its unit (and its day one of the unit's days), and
    #    a review is its assessment's final review.
    by_date = {day.date: day for day in calendar.days}
    by_id = {a.id: a for a in upcoming}
    reviewed: set[UUID] = set()
    for kept in fixed:
        kept_day = by_date.get(kept.start.astimezone(request.timezone).date())
        if kept_day is None:
            continue
        assessment = by_id.get(kept.assessment_id) or AssessmentInput(
            kept.assessment_id, kept.module_id, kept.end, None, ()
        )
        held = _Placed(0, 0, assessment, kept.topic_id, kept.kind, kept.reason, kept)
        length = round((kept.end - kept.start).total_seconds() / 60)
        calendar.place((kept_day, round(_minutes(kept.start)), length), held)
        if kept.kind == "review":
            reviewed.add(kept.assessment_id)
        elif kept.topic_id in topics:
            topics[kept.topic_id].scheduled += length
            topics[kept.topic_id].days.add(kept_day.date)

    # 1. A final review in the 3 days before each exam, test or quiz, as late as fits.
    for assessment in upcoming:
        if not found.covered[assessment.id]:
            shortfalls.append(Shortfall("no_topics", assessment.id))
            continue
        if assessment.kind not in REVIEW_KINDS or assessment.id in reviewed:
            continue
        lo = max(start, _ceil5(_minutes(assessment.due_at - timedelta(days=REVIEW_DAYS))))
        spot = calendar.latest(lo, _floor5(_minutes(assessment.due_at)))
        if spot is None:
            shortfalls.append(Shortfall("no_review_time", assessment.id))
        else:
            calendar.place(spot, _Placed(0, 0, assessment, None, "review", "final_review"))

    def put(topic: _Topic, spot: Spot) -> None:
        # The reason is set at the end, in time order.
        block = _Placed(0, 0, topic.assessment, topic.input.id, "study", "workload")
        calendar.place(spot, block)
        topic.scheduled += spot[2]
        topic.days.add(spot[0].date)

    # 2. Two blocks per topic on different days. A later assessment looks first at the days
    #    after the previous deadline, leaving the earlier days to the earlier assessment.
    previous: date | None = None
    for assessment, group in groups:
        due = _floor5(_minutes(assessment.due_at))
        for round_ in range(MIN_BLOCKS):
            for topic in group:
                if len(topic.days) != round_:
                    continue
                spot = calendar.earliest(due, topic.days, previous)
                if spot is not None:
                    put(topic, spot)
        previous = assessment.due_at.astimezone(request.timezone).date()

    # 3. The rest of each topic's workload, one block per topic per round.
    for assessment, group in groups:
        due = _floor5(_minutes(assessment.due_at))
        pending = [t for t in group if t.scheduled < t.required]
        while pending:
            for topic in list(pending):
                spot = calendar.spread(topic, due)
                if spot is not None:
                    put(topic, spot)
                if spot is None or topic.scheduled >= topic.required:
                    pending.remove(topic)

    for assessment, group in groups:
        for topic in group:
            numbers = (assessment.id, topic.input.id, topic.required, topic.scheduled)
            if topic.input.workload_minutes is None:
                shortfalls.append(Shortfall("no_estimate", *numbers))
            if topic.scheduled < topic.required:
                shortfalls.append(Shortfall("not_enough_time", *numbers))
            if len(topic.days) < MIN_BLOCKS:
                shortfalls.append(Shortfall("not_spaced", *numbers))

    # Reasons in time order: a topic's first block on a second day is its spacing block.
    placed = sorted(
        ((b, day.date) for day in calendar.days for b in day.blocks), key=lambda p: p[0].start
    )
    first_day: dict[UUID, date] = {}
    spaced: set[UUID] = set()
    # A fixed block keeps its reason but still plays its part: first day, or spacing.
    for block, day in placed:
        if block.topic_id is None:
            continue
        if (
            block.topic_id in first_day
            and block.topic_id not in spaced
            and day != first_day[block.topic_id]
        ):
            spaced.add(block.topic_id)
            if block.fixed is None:
                block.reason = "spacing"
        else:
            first_day.setdefault(block.topic_id, day)
            if block.fixed is None:
                block.reason = _study_reason(topics[block.topic_id], block.start)
    blocks = tuple(
        b.fixed
        or Block(
            start=_datetime(b.start),
            end=_datetime(b.end),
            module_id=b.assessment.module_id,
            assessment_id=b.assessment.id,
            topic_id=b.topic_id,
            kind=b.kind,
            reason=b.reason,
        )
        for b, _ in placed
    )
    # Fixed blocks outside the calendar's days (none in practice) still come back.
    outside = tuple(b for b in fixed if b not in blocks)
    if outside:
        blocks = tuple(sorted(blocks + outside, key=lambda b: (b.start, b.end)))
    return Plan(blocks, tuple(shortfalls))
