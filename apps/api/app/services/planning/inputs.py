"""The planner's inputs, read from the database (decision 0018). Async, read-only, and every
query is scoped by ``user_id``.

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
from app.services.errors import Invalid
from app.services.planning import store
from app.services.planning.availability import MINUTES_PER_DAY, local_to_utc
from app.services.planning.planner import AssessmentInput, PlanInput, TopicInput
from app.services.planning.workload import workload

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


@dataclass(frozen=True)
class TopicFacts:
    name: str
    confidence: int | None
    workload_minutes: int | None
    # "yours" (the student's figure), "estimated" (from its pages) or "none".
    workload_source: Literal["yours", "estimated", "none"]
    slide_pages: int
    text_pages: int
    # Measured: whole minutes of active time, and the sessions they came from.
    studied_minutes: int
    sessions: int


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
    - **Topics** in those assessments: workload (the student's figure, else the estimate of
      decision 0016, else None) and starting confidence.
    - **Studied minutes:** the sum of ``study_sessions.active_seconds`` for sessions on the
      topic, floored to whole minutes. A session on a subtopic counts for that subtopic only.
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
    topic_ids = {t for ids in links.values() for t in ids}

    topics = (
        (
            await session.scalars(
                select(Topic).where(Topic.user_id == user_id, Topic.id.in_(topic_ids))
            )
        ).all()
        if topic_ids
        else []
    )
    pages: dict[uuid.UUID, tuple[int, int]] = {}
    for module_id in {t.module_id for t in topics}:
        pages |= await store.page_kinds(session, module_id, user_id=user_id)

    studied: dict[uuid.UUID, tuple[int, int]] = {}
    if topic_ids:
        for on_topic, seconds, count in await session.execute(
            select(StudySession.topic_id, func.sum(StudySession.active_seconds), func.count())
            .where(StudySession.user_id == user_id, StudySession.topic_id.in_(topic_ids))
            .group_by(StudySession.topic_id)
        ):
            if on_topic is not None:
                studied[on_topic] = (math.floor((seconds or 0) / 60), int(count))

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

    topic_facts: dict[uuid.UUID, TopicFacts] = {}
    for topic in topics:
        slides, text = pages.get(topic.id, (0, 0))
        load = workload(topic.estimated_minutes, slides, text)
        minutes, sessions = studied.get(topic.id, (0, 0))
        topic_facts[topic.id] = TopicFacts(
            name=topic.name,
            confidence=topic.confidence,
            workload_minutes=load.minutes,
            workload_source=load.source,
            slide_pages=slides,
            text_pages=text,
            studied_minutes=minutes,
            sessions=sessions,
        )

    def weight(a: Assessment) -> float | None:
        return None if a.weight is None else float(a.weight)

    request = PlanInput(
        now=now,
        free=tuple(i for day in free_days for i in day.intervals),
        daily_cap_minutes=user.daily_study_cap_minutes,
        timezone=tz,
        assessments=tuple(
            AssessmentInput(a.id, a.module_id, a.due_at, weight(a), tuple(sorted(links[a.id])))
            for a in planned
            if a.due_at is not None
        ),
        topics=tuple(
            TopicInput(t.id, t.module_id, topic_facts[t.id].workload_minutes, t.confidence)
            for t in topics
        ),
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
            a.id: AssessmentFacts(a.title, a.module_id, a.due_at, weight(a))
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
