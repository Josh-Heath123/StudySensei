"""An assessment and its topic scope are written together or not at all."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Assessment
from app.schemas.academics import AssessmentCreate, AssessmentUpdate, TopicCreate
from app.services.academics import assessments, topics
from app.services.errors import Invalid, NotFound
from tests.academics.conftest import Rows, make_rows


async def count_assessments(session: AsyncSession, rows: Rows) -> int:
    query = select(func.count()).select_from(Assessment).where(Assessment.user_id == rows.user.id)
    return await session.scalar(query) or 0


async def test_create_with_topics(session: AsyncSession, alice: Rows) -> None:
    second = await topics.create_topic(
        session, alice.module.id, TopicCreate(name="Queues"), user_id=alice.user.id
    )

    exam = await assessments.create_assessment(
        session,
        alice.module.id,
        AssessmentCreate(title="Exam", kind="exam", topic_ids=[alice.topic.id, second.id]),
        user_id=alice.user.id,
    )

    ids = await assessments.get_assessment_topic_ids(session, exam.id, user_id=alice.user.id)
    assert ids == {alice.topic.id, second.id}


@pytest.mark.parametrize("whose", ["another user's", "another module's"])
async def test_create_with_a_bad_topic_writes_nothing(
    session: AsyncSession, alice: Rows, bob: Rows, whose: str
) -> None:
    other_topic = (
        bob.topic
        if whose == "another user's"
        else (await make_rows(session, alice.user, "X1")).topic
    )
    before = await count_assessments(session, alice)

    with pytest.raises(NotFound if whose == "another user's" else Invalid):
        await assessments.create_assessment(
            session,
            alice.module.id,
            AssessmentCreate(title="Exam", kind="exam", topic_ids=[alice.topic.id, other_topic.id]),
            user_id=alice.user.id,
        )

    assert await count_assessments(session, alice) == before


async def test_update_with_a_bad_topic_changes_nothing(
    session: AsyncSession, alice: Rows, bob: Rows
) -> None:
    with pytest.raises(NotFound):
        await assessments.update_assessment(
            session,
            alice.assessment.id,
            AssessmentUpdate(title="Renamed", topic_ids=[bob.topic.id]),
            user_id=alice.user.id,
        )

    fresh = await assessments.get_assessment(session, alice.assessment.id, user_id=alice.user.id)
    assert fresh.title == "Semester test 1"
    ids = await assessments.get_assessment_topic_ids(
        session, alice.assessment.id, user_id=alice.user.id
    )
    assert ids == {alice.topic.id}


async def test_empty_list_clears_and_omitted_keeps(session: AsyncSession, alice: Rows) -> None:
    uid = alice.user.id
    await assessments.update_assessment(
        session, alice.assessment.id, AssessmentUpdate(title="Kept topics"), user_id=uid
    )
    assert await assessments.get_assessment_topic_ids(
        session, alice.assessment.id, user_id=uid
    ) == {alice.topic.id}

    await assessments.update_assessment(
        session, alice.assessment.id, AssessmentUpdate(topic_ids=[]), user_id=uid
    )
    assert (
        await assessments.get_assessment_topic_ids(session, alice.assessment.id, user_id=uid)
        == set()
    )


async def test_batch_lookup_ignores_other_users_assessments(
    session: AsyncSession, alice: Rows, bob: Rows
) -> None:
    found = await assessments.topic_ids_for(
        session, [alice.assessment.id, bob.assessment.id], user_id=alice.user.id
    )

    assert found == {alice.assessment.id: {alice.topic.id}, bob.assessment.id: set()}
