"""Planner v1: what to study, when. A pure function of its inputs (decision 0017).

No database, no clock, no AI: ``plan()`` takes a ``PlanInput`` and returns the same ``Plan``
for the same input, whatever order its lists come in. It works in three passes, sooner
deadlines first:

1. **Final reviews:** one block in the 3 days before each assessment, as late as fits.
2. **Two spaced blocks per topic** on different local days, as early as fits. A later
   assessment's topics look first at the days after the previous deadline.
3. **The rest of each topic's workload,** one block per topic per round, preferring a day
   the topic doesn't have yet, then a spot that isn't next to its own block.

Times are on a 5-minute grid (free time is rounded inward to it). Blocks are 50 minutes, or
25 where a 50 doesn't fit, with the timer's 10-minute break between neighbours. Task 3 turns
the shortfalls into the feasibility report and the reasons into text; task 4 stores blocks.
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
# Starting confidence → percent of the remaining workload. Not rated counts as 3.
CONFIDENCE_PERCENT = {1: 150, 2: 125, 3: 100, 4: 85, 5: 70}


@dataclass(frozen=True)
class AssessmentInput:
    id: UUID
    module_id: UUID
    due_at: datetime
    # 0-100, or None (sorts as 0).
    weight: float | None
    topic_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class TopicInput:
    id: UUID
    module_id: UUID
    # The student's figure, else the estimate (decision 0016), else None.
    workload_minutes: int | None
    # Self-rated 1-5, or None for not rated.
    confidence: int | None


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


BlockKind = Literal["study", "review"]
Reason = Literal[
    "final_review",  # the review in the days before an assessment
    "spacing",  # a topic's first block on a second day
    "no_estimate",  # a topic with no workload figure gets its two default blocks
    "low_confidence",  # the topic is rated 1 or 2
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


def required_minutes(topic: TopicInput, studied: int) -> int:
    """What a topic still needs, rounded up to 5 minutes: ``max(0, workload - studied)``
    scaled by confidence (``CONFIDENCE_PERCENT``). A topic with no workload figure needs its
    two default blocks, less what's been studied."""
    if topic.workload_minutes is None:
        return max(0, MIN_BLOCKS * BLOCK_MINUTES - studied)
    remaining = max(0, topic.workload_minutes - studied)
    percent = CONFIDENCE_PERCENT.get(topic.confidence or 3, 100)
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
        """Whether the block right before or right after [start, end) is on ``topic_id``."""
        before = [b for b in self.blocks if b.end <= start][-1:]
        after = [b for b in self.blocks if b.start >= end][:1]
        return any(b.topic_id == topic_id for b in before + after)


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
            days.append(_Day(day, day_start, day_end, pieces))
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
        """An extra block before ``hi``: the earliest spot on a day without the topic, else
        the earliest not next to the topic's own block, else the earliest."""
        best: tuple[int, int, Spot] | None = None
        for day in self.days:
            if day.start >= hi:
                break
            for gap in day.gaps(self.start, hi):
                length = day.length_for(gap, self.cap)
                if length is None:
                    continue
                start = gap[0]
                if day.date not in topic.days:
                    return day, start, length
                level = 2 if day.next_to(start, start + length, topic.input.id) else 1
                if best is None or (level, start) < best[:2]:
                    best = (level, start, (day, start, length))
        return None if best is None else best[2]


def _assessment_key(assessment: AssessmentInput) -> tuple[datetime, float, str]:
    """Sooner deadlines first, then higher weight, then the id (stable)."""
    return (assessment.due_at, -(assessment.weight or 0), str(assessment.id))


def _topic_key(topic: _Topic) -> tuple[int, str]:
    """Within an assessment: lower confidence first, then the id (stable)."""
    return (topic.input.confidence or 3, str(topic.input.id))


def _study_reason(topic: _Topic, start: int) -> Reason:
    if topic.input.workload_minutes is None:
        return "no_estimate"
    if (topic.input.confidence or 3) <= 2:
        return "low_confidence"
    if _minutes(topic.assessment.due_at) - start <= URGENT_DAYS * MINUTES_PER_DAY:
        return "urgency"
    return "workload"


def plan(request: PlanInput) -> Plan:
    """The plan for ``request`` (see the module docstring and decision 0017)."""
    start = _ceil5(_minutes(request.now))
    upcoming = sorted(
        (a for a in request.assessments if a.due_at > request.now), key=_assessment_key
    )
    if not upcoming:
        return Plan((), ())
    topics_by_id = {t.id: t for t in request.topics}

    def covered(assessment: AssessmentInput) -> list[UUID]:
        ids = {
            i
            for i in assessment.topic_ids
            if i in topics_by_id and topics_by_id[i].module_id == assessment.module_id
        }
        return sorted(ids, key=str)

    # Each topic with work left is planned for the soonest assessment that covers it.
    topics: dict[UUID, _Topic] = {}
    for assessment in upcoming:
        for topic_id in covered(assessment):
            need = required_minutes(
                topics_by_id[topic_id], request.studied_minutes.get(topic_id, 0)
            )
            if topic_id not in topics and need > 0:
                topics[topic_id] = _Topic(topics_by_id[topic_id], assessment, need)
    groups = [
        (a, sorted((t for t in topics.values() if t.assessment.id == a.id), key=_topic_key))
        for a in upcoming
    ]
    groups = [(a, group) for a, group in groups if group]

    calendar = _Calendar(request, start, _floor5(_minutes(upcoming[-1].due_at)))
    shortfalls: list[Shortfall] = []

    # 1. A final review in the 3 days before each assessment, as late as fits.
    for assessment in upcoming:
        if not covered(assessment):
            shortfalls.append(Shortfall("no_topics", assessment.id))
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
    for block, day in placed:
        if block.topic_id is None:
            continue
        if (
            block.topic_id in first_day
            and block.topic_id not in spaced
            and day != first_day[block.topic_id]
        ):
            spaced.add(block.topic_id)
            block.reason = "spacing"
        else:
            first_day.setdefault(block.topic_id, day)
            block.reason = _study_reason(topics[block.topic_id], block.start)
    blocks = tuple(
        Block(
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
    return Plan(blocks, tuple(shortfalls))
