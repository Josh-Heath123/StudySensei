"""The planner's inputs, read from the database (decisions 0018 and 0019). Async,
read-only, and every query is scoped by ``user_id``.

``load_plan_data`` returns the ``PlanInput`` for ``plan()`` and the facts the text needs
(names, where each workload figure came from, how many sessions were measured). Nothing here
writes, and nothing is sent to AI.
"""

import math
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Assessment, AssessmentTopic, Module, StudySession, Topic
from app.schemas.planning import MAX_RANGE_DAYS
from app.services.academics.topics import list_topics
from app.services.errors import Invalid
from app.services.planning import store
from app.services.planning.availability import MINUTES_PER_DAY, local_to_utc
from app.services.planning.planner import AssessmentInput, PlanInput, TopicInput
from app.services.planning.subtree import (
    ConfidenceSource,
    Page,
    Tree,
    ancestors,
    subtree,
    subtree_confidence,
    subtree_workload,
    units,
)

DEFAULT_DAYS = 28


@dataclass(frozen=True)
class ModuleFacts:
    code: str
    colour: str


@dataclass(frozen=True)
class AssessmentFacts:
    title: str
    module_id: uuid.UUID
    due_at: datetime
    weight: float | None
    kind: str = "exam"


@dataclass(frozen=True)
class TopicFacts:
    name: str
    confidence: int | None
    workload_minutes: int | None
    # "yours" (the student's figure), "estimated" (from its pages) or "none".
    workload_source: Literal["yours", "estimated", "none"]
    slide_pages: int
    text_pages: int
    # Measured: whole minutes of active time, and the sessions they came from (on the topic
    # or any subtopic).
    studied_minutes: int
    sessions: int
    # How many topics are under it: its workload and sessions include theirs (decision 0019).
    subtopics: int = 0
    # "yours" (its own rating), "subtopics" (their mean) or "none".
    confidence_source: ConfidenceSource = "none"


@dataclass(frozen=True)
class PlanFacts:
    timezone: ZoneInfo
    daily_cap_minutes: int
    # The local dates the free time covers (inclusive).
    first: date
    last: date
    modules: Mapping[uuid.UUID, ModuleFacts]
    # Every upcoming assessment, including those due after ``last`` (which aren't planned).
    assessments: Mapping[uuid.UUID, AssessmentFacts]
    topics: Mapping[uuid.UUID, TopicFacts]
    # Upcoming assessments due after the window: listed, not planned.
    later: tuple[uuid.UUID, ...]


@dataclass(frozen=True)
class PlanData:
    input: PlanInput
    facts: PlanFacts


async def load_plan_data(
    session: AsyncSession, *, user_id: uuid.UUID, now: datetime, days: int = DEFAULT_DAYS
) -> PlanData:
    """Everything ``plan()`` needs for the ``days`` local dates from today (1 to 62, like
    ``GET /availability``), and the facts behind it.

    - **Free time:** ``availability.expand()`` in the user's timezone, with the daily cap.
    - **Assessments:** status "upcoming", due after ``now`` and by the end of the window.
      Later ones are listed in ``facts.later`` and not planned: there's no free time for
      them in the window yet.
    - **Units** (decision 0019): each ticked topic with no ticked ancestor stands for its
      whole subtree, with its workload, confidence and studied minutes from ``subtree.py``.
      A unit inside a sooner assessment's unit becomes that unit.
    - **Studied minutes:** the sum of ``study_sessions.active_seconds`` for sessions on the
      unit or any topic under it, floored to whole minutes.
    """
    if not 1 <= days <= MAX_RANGE_DAYS:
        raise Invalid(f"Plan between 1 and {MAX_RANGE_DAYS} days.")
    user = await store.get_settings(session, user_id=user_id)
    tz = ZoneInfo(user.timezone)
    first = now.astimezone(tz).date()
    last = first + timedelta(days=days - 1)
    _, free_days, _ = await store.availability(session, first, last, user_id=user_id)
    # The window ends at the local midnight after its last date.
    end = local_to_utc(last, MINUTES_PER_DAY, tz)

    found = (
        await session.scalars(
            select(Assessment)
            .where(
                Assessment.user_id == user_id,
                Assessment.status == "upcoming",
                Assessment.due_at.is_not(None),
                Assessment.due_at > now,
            )
            .order_by(Assessment.due_at, Assessment.id)
        )
    ).all()
    planned = [a for a in found if a.due_at is not None and a.due_at <= end]
    later = tuple(a.id for a in found if a.due_at is not None and a.due_at > end)

    links: dict[uuid.UUID, list[uuid.UUID]] = {a.id: [] for a in planned}
    if links:
        for assessment_id, topic_id in await session.execute(
            select(AssessmentTopic.assessment_id, AssessmentTopic.topic_id)
            .join(Assessment, Assessment.id == AssessmentTopic.assessment_id)
            .where(Assessment.user_id == user_id, AssessmentTopic.assessment_id.in_(links))
        ):
            links[assessment_id].append(topic_id)

    # Every topic of the planned assessments' modules: units are whole subtrees.
    trees: dict[uuid.UUID, Tree] = {}
    by_id: dict[uuid.UUID, Topic] = {}
    pages: dict[uuid.UUID, set[Page]] = {}
    for module_id in sorted({a.module_id for a in planned}, key=str):
        module_topics = await list_topics(session, module_id, user_id=user_id)
        trees[module_id] = store.topic_tree(module_topics)
        by_id |= {t.id: t for t in module_topics}
        pages |= await store.topic_pages(session, module_id, user_id=user_id)

    measured: dict[uuid.UUID, tuple[float, int]] = {}
    if trees:
        for on_topic, seconds, count in await session.execute(
            select(StudySession.topic_id, func.sum(StudySession.active_seconds), func.count())
            .where(
                StudySession.user_id == user_id,
                StudySession.module_id.in_(trees),
                StudySession.topic_id.is_not(None),
            )
            .group_by(StudySession.topic_id)
        ):
            if on_topic is not None:
                measured[on_topic] = (float(seconds or 0), int(count))

    # Each assessment's units, sooner assessments first (the planner's order). A unit inside a
    # sooner assessment's unit is that unit, so the planner plans it once, for the sooner one.
    def priority(a: Assessment) -> tuple[datetime, float, str]:
        assert a.due_at is not None
        return (a.due_at, -float(a.weight or 0), str(a.id))

    unit_links: dict[uuid.UUID, tuple[uuid.UUID, ...]] = {}
    taken: set[uuid.UUID] = set()
    for a in sorted(planned, key=priority):
        tree = trees[a.module_id]
        ticked = [t for t in links[a.id] if t in by_id and by_id[t].module_id == a.module_id]
        found_units: list[uuid.UUID] = []
        for unit in units(tree, ticked):
            holder = next((t for t in [unit, *ancestors(tree, unit)] if t in taken), unit)
            if holder not in found_units:
                found_units.append(holder)
        unit_links[a.id] = tuple(found_units)
        taken |= set(found_units)

    topic_facts: dict[uuid.UUID, TopicFacts] = {}
    topic_inputs: list[TopicInput] = []
    for unit in sorted(taken, key=str):
        topic = by_id[unit]
        tree = trees[topic.module_id]
        members = subtree(tree, unit)
        load = subtree_workload(tree, unit, topic.estimated_minutes, pages)
        confidence, confidence_source = subtree_confidence(
            tree, unit, {t: by_id[t].confidence for t in members}
        )
        seconds = sum(measured.get(t, (0.0, 0))[0] for t in members)
        topic_facts[unit] = TopicFacts(
            name=topic.name,
            confidence=confidence,
            workload_minutes=load.workload.minutes,
            workload_source=load.workload.source,
            slide_pages=load.workload.slide_pages,
            text_pages=load.workload.text_pages,
            studied_minutes=math.floor(seconds / 60),
            sessions=sum(measured.get(t, (0.0, 0))[1] for t in members),
            subtopics=load.subtopics,
            confidence_source=confidence_source,
        )
        topic_inputs.append(
            TopicInput(unit, topic.module_id, load.workload.minutes, confidence, tree.order[unit])
        )

    module_ids = {a.module_id for a in found}
    modules = (
        (
            await session.scalars(
                select(Module).where(Module.user_id == user_id, Module.id.in_(module_ids))
            )
        ).all()
        if module_ids
        else []
    )

    def weight(a: Assessment) -> float | None:
        return None if a.weight is None else float(a.weight)

    request = PlanInput(
        now=now,
        free=tuple(i for day in free_days for i in day.intervals),
        daily_cap_minutes=user.daily_study_cap_minutes,
        timezone=tz,
        assessments=tuple(
            AssessmentInput(
                a.id, a.module_id, a.due_at, weight(a), tuple(sorted(unit_links[a.id])), a.kind
            )
            for a in planned
            if a.due_at is not None
        ),
        topics=tuple(topic_inputs),
        studied_minutes={
            t: facts.studied_minutes for t, facts in topic_facts.items() if facts.studied_minutes
        },
    )
    facts = PlanFacts(
        timezone=tz,
        daily_cap_minutes=user.daily_study_cap_minutes,
        first=first,
        last=last,
        modules={m.id: ModuleFacts(m.code, m.colour) for m in modules},
        assessments={
            a.id: AssessmentFacts(a.title, a.module_id, a.due_at, weight(a), a.kind)
            for a in found
            if a.due_at is not None
        },
        topics=topic_facts,
        later=later,
    )
    return PlanData(request, facts)


async def build_plan_input(
    session: AsyncSession, *, user_id: uuid.UUID, now: datetime, days: int = DEFAULT_DAYS
) -> PlanInput:
    """Just the ``PlanInput`` (see ``load_plan_data``)."""
    return (await load_plan_data(session, user_id=user_id, now=now, days=days)).input
