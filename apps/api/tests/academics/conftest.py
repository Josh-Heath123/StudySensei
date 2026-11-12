from dataclasses import dataclass

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Assessment, Module, Task, Topic, User
from app.schemas.academics import AssessmentCreate, ModuleCreate, TaskCreate, TopicCreate
from app.services.academics import assessments, modules, tasks, topics


@dataclass
class Rows:
    """One of everything, owned by a single user."""

    user: User
    module: Module
    topic: Topic
    assessment: Assessment
    task: Task


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
    return Rows(user, module, topic, assessment, task)


@pytest.fixture
async def alice(session: AsyncSession, user_a: User) -> Rows:
    return await make_rows(session, user_a)


@pytest.fixture
async def bob(session: AsyncSession, user_b: User) -> Rows:
    # Same module code as Alice on purpose: codes are unique per user, not globally.
    return await make_rows(session, user_b)
