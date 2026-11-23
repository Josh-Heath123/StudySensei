"""Topic mastery (ADR 0027): computed on read, never stored. Thin: ``services/mastery`` does
the work."""

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.core import clock
from app.core.db import SessionDep
from app.schemas.mastery import ModuleMasteryOut, TopicMasteryOut, topic_mastery_out
from app.services.mastery.load import module_mastery, one_topic_mastery

router = APIRouter(tags=["mastery"])


@router.get("/modules/{module_id}/mastery", response_model=ModuleMasteryOut)
async def get_module_mastery(
    module_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> ModuleMasteryOut:
    """Every topic in tree order with its mastery now: an estimate of how well you know it, from
    your reviews, Quiz me answers and ratings. Never an exam prediction."""
    at = clock.now()
    found = await module_mastery(session, module_id, user_id=user.id, at=at)
    return ModuleMasteryOut(
        module_id=module_id, at=at, topics=[topic_mastery_out(t) for t in found]
    )


@router.get("/topics/{topic_id}/mastery", response_model=TopicMasteryOut)
async def get_topic_mastery(
    topic_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> TopicMasteryOut:
    """One topic's mastery now (its subtree's practice; see the module endpoint)."""
    found = await one_topic_mastery(session, topic_id, user_id=user.id, at=clock.now())
    return topic_mastery_out(found)
