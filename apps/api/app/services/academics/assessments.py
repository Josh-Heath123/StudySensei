import uuid
from collections.abc import Collection

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.queue import enqueue_replan
from app.models import Assessment, AssessmentTopic, Topic
from app.schemas.academics import AssessmentCreate, AssessmentUpdate
from app.services.academics.modules import get_module
from app.services.errors import Invalid, NotFound


async def list_assessments(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    module_id: uuid.UUID | None = None,
    statuses: Collection[str] = (),
) -> list[Assessment]:
    """The user's assessments, soonest first (undated ones last).

    With ``module_id``, only that module's (NotFound if it isn't the user's);
    with ``statuses``, only those statuses.
    """
    query = select(Assessment).where(Assessment.user_id == user_id)
    if module_id is not None:
        await get_module(session, module_id, user_id=user_id)
        query = query.where(Assessment.module_id == module_id)
    if statuses:
        query = query.where(Assessment.status.in_(statuses))
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


async def _check_topics(
    session: AsyncSession,
    topic_ids: set[uuid.UUID],
    module_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
) -> None:
    """Every topic must exist and be the user's (else NotFound) and be in ``module_id``."""
    if not topic_ids:
        return
    topics = list(
        await session.scalars(
            select(Topic).where(Topic.id.in_(topic_ids), Topic.user_id == user_id)
        )
    )
    if len(topics) != len(topic_ids):
        raise NotFound("Topic")
    if any(t.module_id != module_id for t in topics):
        raise Invalid("An assessment can only cover topics from its own module")


async def _replace_topics(
    session: AsyncSession, assessment: Assessment, topic_ids: set[uuid.UUID]
) -> None:
    """Swap the assessment's topic links for ``topic_ids`` (already checked). No commit."""
    await session.execute(
        delete(AssessmentTopic).where(AssessmentTopic.assessment_id == assessment.id)
    )
    session.add_all(
        AssessmentTopic(
            assessment_id=assessment.id, topic_id=topic_id, module_id=assessment.module_id
        )
        for topic_id in topic_ids
    )


async def _replan(session: AsyncSession, assessment: Assessment, *, user_id: uuid.UUID) -> None:
    """Queue a re-plan for this change (decision 0021), named for the summary."""
    module = await get_module(session, assessment.module_id, user_id=user_id)
    await enqueue_replan(
        session,
        user_id=user_id,
        trigger="assessment",
        detail={"assessment_id": str(assessment.id), "name": f"{module.code} {assessment.title}"},
    )


async def create_assessment(
    session: AsyncSession, module_id: uuid.UUID, data: AssessmentCreate, *, user_id: uuid.UUID
) -> Assessment:
    """Create the assessment and its topic links together. Topics are checked first,
    so a bad topic ID writes nothing."""
    await get_module(session, module_id, user_id=user_id)
    topic_ids = set(data.topic_ids)
    await _check_topics(session, topic_ids, module_id, user_id=user_id)

    assessment = Assessment(
        user_id=user_id, module_id=module_id, **data.model_dump(exclude={"topic_ids"})
    )
    session.add(assessment)
    await session.flush()
    await _replace_topics(session, assessment, topic_ids)
    await _replan(session, assessment, user_id=user_id)
    await session.commit()
    return assessment


async def update_assessment(
    session: AsyncSession, assessment_id: uuid.UUID, data: AssessmentUpdate, *, user_id: uuid.UUID
) -> Assessment:
    """Apply the fields sent. ``topic_ids``, if sent, replaces the whole set. All checks
    run before anything changes, so a bad topic leaves the assessment untouched."""
    assessment = await get_assessment(session, assessment_id, user_id=user_id)
    changes = data.model_dump(exclude_unset=True)
    new_topics: list[uuid.UUID] | None = changes.pop("topic_ids", None)
    if new_topics is not None:
        await _check_topics(session, set(new_topics), assessment.module_id, user_id=user_id)

    for name, value in changes.items():
        setattr(assessment, name, value)
    if new_topics is not None:
        await _replace_topics(session, assessment, set(new_topics))
    await _replan(session, assessment, user_id=user_id)
    await session.commit()
    return assessment


async def delete_assessment(
    session: AsyncSession, assessment_id: uuid.UUID, *, user_id: uuid.UUID
) -> None:
    """Deletes the assessment and its topic links; its tasks stay, unlinked."""
    assessment = await get_assessment(session, assessment_id, user_id=user_id)
    await _replan(session, assessment, user_id=user_id)
    await session.delete(assessment)
    await session.commit()


async def topic_ids_for(
    session: AsyncSession, assessment_ids: list[uuid.UUID], *, user_id: uuid.UUID
) -> dict[uuid.UUID, set[uuid.UUID]]:
    """Topic IDs for many assessments in one query (only the user's assessments)."""
    found: dict[uuid.UUID, set[uuid.UUID]] = {a: set() for a in assessment_ids}
    rows = await session.execute(
        select(AssessmentTopic.assessment_id, AssessmentTopic.topic_id)
        .join(Assessment, Assessment.id == AssessmentTopic.assessment_id)
        .where(AssessmentTopic.assessment_id.in_(assessment_ids), Assessment.user_id == user_id)
    )
    for assessment_id, topic_id in rows:
        found[assessment_id].add(topic_id)
    return found


async def get_assessment_topic_ids(
    session: AsyncSession, assessment_id: uuid.UUID, *, user_id: uuid.UUID
) -> set[uuid.UUID]:
    await get_assessment(session, assessment_id, user_id=user_id)
    return (await topic_ids_for(session, [assessment_id], user_id=user_id))[assessment_id]


async def set_assessment_topics(
    session: AsyncSession,
    assessment_id: uuid.UUID,
    topic_ids: set[uuid.UUID],
    *,
    user_id: uuid.UUID,
) -> set[uuid.UUID]:
    """Replace the topics an assessment covers. All must be in its module."""
    await update_assessment(
        session, assessment_id, AssessmentUpdate(topic_ids=list(topic_ids)), user_id=user_id
    )
    return topic_ids
