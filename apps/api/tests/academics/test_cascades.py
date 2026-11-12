from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Assessment, AssessmentTopic, Task, Topic
from app.schemas.academics import TaskCreate, TaskUpdate, TopicCreate
from app.services.academics import assessments, modules, tasks, topics
from app.services.errors import Invalid
from tests.academics.conftest import Rows, make_rows


async def count(session: AsyncSession, model: Any, **filters: Any) -> int:
    query = select(func.count()).select_from(model)
    for column, value in filters.items():
        query = query.where(getattr(model, column) == value)
    return await session.scalar(query) or 0


async def test_deleting_a_module_removes_everything_in_it(
    session: AsyncSession, alice: Rows
) -> None:
    other = await make_rows(session, alice.user, code="COS301")

    await modules.delete_module(session, alice.module.id, user_id=alice.user.id)

    for model in (Topic, Assessment, Task, AssessmentTopic):
        assert await count(session, model, module_id=alice.module.id) == 0
        assert await count(session, model, module_id=other.module.id) == 1


async def test_deleting_an_assessment_unlinks_its_tasks(session: AsyncSession, alice: Rows) -> None:
    await assessments.delete_assessment(session, alice.assessment.id, user_id=alice.user.id)

    task = await tasks.get_task(session, alice.task.id, user_id=alice.user.id)
    await session.refresh(task)
    assert task.assessment_id is None
    assert task.module_id == alice.module.id
    assert await count(session, AssessmentTopic, assessment_id=alice.assessment.id) == 0


async def test_deleting_a_topic_removes_its_assessment_links(
    session: AsyncSession, alice: Rows
) -> None:
    await topics.delete_topic(session, alice.topic.id, user_id=alice.user.id)

    ids = await assessments.get_assessment_topic_ids(
        session, alice.assessment.id, user_id=alice.user.id
    )
    assert ids == set()


async def test_set_assessment_topics_replaces_the_scope(session: AsyncSession, alice: Rows) -> None:
    other_topic = await topics.create_topic(
        session, alice.module.id, TopicCreate(name="Queues"), user_id=alice.user.id
    )

    await assessments.set_assessment_topics(
        session, alice.assessment.id, {other_topic.id}, user_id=alice.user.id
    )

    ids = await assessments.get_assessment_topic_ids(
        session, alice.assessment.id, user_id=alice.user.id
    )
    assert ids == {other_topic.id}


async def test_assessment_topics_must_share_its_module(session: AsyncSession, alice: Rows) -> None:
    other = await make_rows(session, alice.user, code="COS301")

    with pytest.raises(Invalid):
        await assessments.set_assessment_topics(
            session, alice.assessment.id, {other.topic.id}, user_id=alice.user.id
        )


async def test_task_completed_at_follows_status(session: AsyncSession, alice: Rows) -> None:
    uid = alice.user.id
    task = await tasks.create_task(
        session, alice.module.id, TaskCreate(title="Done already", status="done"), user_id=uid
    )
    assert task.completed_at is not None

    task = await tasks.update_task(session, task.id, TaskUpdate(status="todo"), user_id=uid)
    assert task.completed_at is None


async def test_task_assessment_must_share_its_module(session: AsyncSession, alice: Rows) -> None:
    other = await make_rows(session, alice.user, code="COS301")

    with pytest.raises(Invalid):
        await tasks.create_task(
            session,
            other.module.id,
            TaskCreate(title="X", assessment_id=alice.assessment.id),
            user_id=alice.user.id,
        )
