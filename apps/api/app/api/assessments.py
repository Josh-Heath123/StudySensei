import uuid

from fastapi import APIRouter, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.core.db import SessionDep
from app.models import Assessment
from app.schemas.academics import (
    AssessmentCreate,
    AssessmentFields,
    AssessmentOut,
    AssessmentUpdate,
)
from app.services.academics import assessments

router = APIRouter(tags=["assessments"])


async def _with_topics(
    session: AsyncSession, items: list[Assessment], *, user_id: uuid.UUID
) -> list[AssessmentOut]:
    topic_ids = await assessments.topic_ids_for(session, [a.id for a in items], user_id=user_id)
    return [
        AssessmentOut(
            **AssessmentFields.model_validate(a).model_dump(), topic_ids=sorted(topic_ids[a.id])
        )
        for a in items
    ]


async def _one(session: AsyncSession, item: Assessment, *, user_id: uuid.UUID) -> AssessmentOut:
    return (await _with_topics(session, [item], user_id=user_id))[0]


@router.get("/assessments", response_model=list[AssessmentOut])
async def list_assessments(
    session: SessionDep, user: CurrentUser, module_id: uuid.UUID | None = None
) -> list[AssessmentOut]:
    """Your assessments, soonest first (undated last), optionally for one module."""
    items = await assessments.list_assessments(session, user_id=user.id, module_id=module_id)
    return await _with_topics(session, items, user_id=user.id)


@router.post(
    "/modules/{module_id}/assessments",
    response_model=AssessmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_assessment(
    module_id: uuid.UUID, data: AssessmentCreate, session: SessionDep, user: CurrentUser
) -> AssessmentOut:
    item = await assessments.create_assessment(session, module_id, data, user_id=user.id)
    return await _one(session, item, user_id=user.id)


@router.get("/assessments/{assessment_id}", response_model=AssessmentOut)
async def get_assessment(
    assessment_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> AssessmentOut:
    item = await assessments.get_assessment(session, assessment_id, user_id=user.id)
    return await _one(session, item, user_id=user.id)


@router.patch("/assessments/{assessment_id}", response_model=AssessmentOut)
async def update_assessment(
    assessment_id: uuid.UUID, data: AssessmentUpdate, session: SessionDep, user: CurrentUser
) -> AssessmentOut:
    """Change the fields sent; ``topic_ids`` replaces the whole set ([] clears it)."""
    item = await assessments.update_assessment(session, assessment_id, data, user_id=user.id)
    return await _one(session, item, user_id=user.id)


@router.delete("/assessments/{assessment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_assessment(
    assessment_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> None:
    """Deletes the assessment; its tasks are kept, unlinked."""
    await assessments.delete_assessment(session, assessment_id, user_id=user.id)
