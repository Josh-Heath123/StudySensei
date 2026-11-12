import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Assessment, AssessmentTopic, Topic
from app.schemas.academics import AssessmentCreate, AssessmentUpdate
from app.services.academics.modules import get_module
from app.services.errors import Invalid, NotFound


async def list_assessments(
    session: AsyncSession, *, user_id: uuid.UUID, module_id: uuid.UUID | None = None
) -> list[Assessment]:
    """The user's assessments, soonest first (undated ones last)."""
    query = select(Assessment).where(Assessment.user_id == user_id)
    if module_id is not None:
        query = query.where(Assessment.module_id == module_id)
    result = await session.scalars(
        query.order_by(Assessment.due_at.asc().nulls_last(), Assessment.title)
    )
    return list(result)


async def get_assessment(
    session: AsyncSession, assessment_id: uuid.UUID, *, user_id: uuid.UUID
) -> Assessment:
    assessment = await session.scalar(
        select(Assessment).where(Assessment.id == assessment_id, Assessment.user_id == user_id)
    )
    if assessment is None:
        raise NotFound("Assessment")
    return assessment


async def create_assessment(
    session: AsyncSession, module_id: uuid.UUID, data: AssessmentCreate, *, user_id: uuid.UUID
) -> Assessment:
    await get_module(session, module_id, user_id=user_id)
    assessment = Assessment(user_id=user_id, module_id=module_id, **data.model_dump())
    session.add(assessment)
    await session.commit()
    return assessment


async def update_assessment(
    session: AsyncSession, assessment_id: uuid.UUID, data: AssessmentUpdate, *, user_id: uuid.UUID
) -> Assessment:
    assessment = await get_assessment(session, assessment_id, user_id=user_id)
    for name, value in data.model_dump(exclude_unset=True).items():
        setattr(assessment, name, value)
    await session.commit()
    return assessment


async def delete_assessment(
    session: AsyncSession, assessment_id: uuid.UUID, *, user_id: uuid.UUID
) -> None:
    """Deletes the assessment and its topic links; its tasks stay, unlinked."""
    assessment = await get_assessment(session, assessment_id, user_id=user_id)
    await session.delete(assessment)
    await session.commit()


async def get_assessment_topic_ids(
    session: AsyncSession, assessment_id: uuid.UUID, *, user_id: uuid.UUID
) -> set[uuid.UUID]:
    await get_assessment(session, assessment_id, user_id=user_id)
    result = await session.scalars(
        select(AssessmentTopic.topic_id).where(AssessmentTopic.assessment_id == assessment_id)
    )
    return set(result)


async def set_assessment_topics(
    session: AsyncSession,
    assessment_id: uuid.UUID,
    topic_ids: set[uuid.UUID],
    *,
    user_id: uuid.UUID,
) -> set[uuid.UUID]:
    """Replace the topics an assessment covers. All must be in its module."""
    assessment = await get_assessment(session, assessment_id, user_id=user_id)
    topics = list(
        await session.scalars(
            select(Topic).where(Topic.id.in_(topic_ids), Topic.user_id == user_id)
        )
    )
    if len(topics) != len(topic_ids):
        raise NotFound("Topic")
    if any(t.module_id != assessment.module_id for t in topics):
        raise Invalid("An assessment can only cover topics from its own module")

    await session.execute(
        delete(AssessmentTopic).where(AssessmentTopic.assessment_id == assessment.id)
    )
    session.add_all(
        AssessmentTopic(
            assessment_id=assessment.id, topic_id=topic_id, module_id=assessment.module_id
        )
        for topic_id in topic_ids
    )
    await session.commit()
    return topic_ids
