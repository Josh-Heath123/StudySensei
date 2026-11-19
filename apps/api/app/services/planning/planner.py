"""Planner v1: who studies what, when. A pure function of its inputs (decision 0017).

No database, no clock, no AI: ``plan()`` takes a ``PlanInput`` and returns the same ``Plan``
for the same input. Task 3 turns the shortfalls into the feasibility report and the reasons
into text; task 4 stores the blocks.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from app.services.planning.availability import Interval

BLOCK_MINUTES = 50
SHORT_BLOCK_MINUTES = 25
BREAK_MINUTES = 10
MIN_BLOCKS = 2
REVIEW_DAYS = 3
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
    "spacing",  # the second of a topic's two minimum blocks, on another day
    "no_estimate",  # a topic with no workload figure gets its two default blocks
    "low_confidence",  # the topic is rated 1 or 2
    "urgency",  # the assessment is due within 7 days
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
    """What a topic still needs: max(0, workload - studied), scaled by confidence and rounded
    up to 5; a topic with no workload figure needs its two default blocks."""
    raise NotImplementedError


def plan(request: PlanInput) -> Plan:
    raise NotImplementedError
