import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Assessment, Job, Module, StudySession, Task, Topic, User
from app.schemas.academics import AssessmentCreate, ModuleCreate, TaskCreate, TopicCreate
from app.schemas.sessions import EventBatch, ReflectionIn, SessionStart
from app.services.academics import assessments, modules, tasks, topics
from app.services.sessions import sessions


@dataclass
class Rows:
    """One of everything, owned by a single user."""

    user: User
    module: Module
    topic: Topic
    assessment: Assessment
    task: Task
    # Ended an hour ago, with a reflection rating ``topic``.
    study_session: StudySession
    start_event_id: uuid.UUID


async def make_rows(session: AsyncSession, user: User, code: str = "COS330") -> Rows:
    uid = user.id
    module = await modules.create_module(
        session, ModuleCreate(code=code, name="Software Architecture"), user_id=uid
    )
    topic = await topics.create_topic(
        session, module.id, TopicCreate(name="Microservices"), user_id=uid
    )
    assessment = await assessments.create_assessment(
        session, module.id, AssessmentCreate(title="Semester test 1", kind="test"), user_id=uid
    )
    await assessments.set_assessment_topics(session, assessment.id, {topic.id}, user_id=uid)
    task = await tasks.create_task(
        session,
        module.id,
        TaskCreate(title="Read chapter 4", assessment_id=assessment.id),
        user_id=uid,
    )
    start_event_id = uuid.uuid4()
    started = datetime.now(UTC) - timedelta(hours=2)
    study = await make_ended_session(session, user, module, topic, start_event_id, started)
    await forget_replans(session, user)
    return Rows(user, module, topic, assessment, task, study, start_event_id)


async def forget_replans(session: AsyncSession, user: User) -> None:
    """Drop the re-plan jobs that setting up rows queued (decision 0021): fixtures aren't
    changes, and job tests expect only their own jobs."""
    await session.execute(delete(Job).where(Job.user_id == user.id, Job.kind == "replan"))
    await session.commit()


async def make_ended_session(
    session: AsyncSession,
    user: User,
    module: Module,
    topic: Topic,
    start_event_id: uuid.UUID,
    started: datetime,
) -> StudySession:
    """A 50-minute session on ``topic`` (one 5-minute break), ended and reflected on."""
    uid = user.id
    start = {"id": start_event_id, "occurred_at": started}
    study, _ = await sessions.start_session(
        session,
        SessionStart.model_validate({"module_id": module.id, "topic_id": topic.id, "start": start}),
        user_id=uid,
    )
    steps = [("break_start", 25), ("break_end", 30), ("end", 55)]
    events = [
        {"id": uuid.uuid4(), "type": kind, "occurred_at": started + timedelta(minutes=minutes)}
        for kind, minutes in steps
    ]
    await sessions.add_events(
        session, study.id, EventBatch.model_validate({"events": events}), user_id=uid
    )
    reflection = {"focus_rating": 4, "topic_ratings": [{"topic_id": topic.id, "confidence": 3}]}
    return await sessions.set_reflection(
        session, study.id, ReflectionIn.model_validate(reflection), user_id=uid
    )


@pytest.fixture
async def alice(session: AsyncSession, user_a: User) -> Rows:
    return await make_rows(session, user_a)


@pytest.fixture
async def bob(session: AsyncSession, user_b: User) -> Rows:
    # Same module code as Alice on purpose: codes are unique per user, not globally.
    return await make_rows(session, user_b)
