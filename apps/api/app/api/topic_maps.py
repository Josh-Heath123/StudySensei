import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.core.db import SessionDep
from app.schemas.topic_maps import ClearedTopics, MaterialTopicStatus, TopicMapStatus
from app.services import topic_maps

router = APIRouter(tags=["topics"])


@router.get("/modules/{module_id}/topic-map", response_model=TopicMapStatus)
async def topic_map_status(
    module_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> TopicMapStatus:
    """How far the AI topic map has got: materials analysed of those eligible, the merge,
    and whether jobs are waiting for AI rate limits to reset (`waiting_until`)."""
    return await topic_maps.topic_map_status(session, module_id, user_id=user.id)


@router.post("/modules/{module_id}/topic-map/build", response_model=TopicMapStatus)
async def build_topic_map(
    module_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> TopicMapStatus:
    """Analyse every eligible material not analysed yet, then merge into the topic tree.

    Existing topics are never renamed, moved or deleted; only new topics are added.
    """
    return await topic_maps.build_topic_map(session, module_id, user_id=user.id)


@router.get("/modules/{module_id}/topic-map/materials", response_model=list[MaterialTopicStatus])
async def material_topic_states(
    module_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> list[MaterialTopicStatus]:
    """Each eligible material's topic extraction: analysed, failed (with why), or waiting."""
    return await topic_maps.material_topic_states(session, module_id, user_id=user.id)


@router.post("/materials/{material_id}/topics/retry", response_model=MaterialTopicStatus)
async def retry_material_topics(
    material_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> MaterialTopicStatus:
    """Find this material's topics again: a new run with a fresh AI call budget.

    422 if its topics aren't extracted (AI off, a kind that isn't analysed, or not ready).
    """
    return await topic_maps.retry_material_topics(session, material_id, user_id=user.id)


@router.delete("/modules/{module_id}/ai-topics", response_model=ClearedTopics)
async def clear_ai_topics(
    module_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> ClearedTopics:
    """Delete every topic still marked AI. Topics the student made or edited stay.

    The materials' proposals are kept, so building again re-merges without re-analysing.
    """
    deleted = await topic_maps.clear_ai_topics(session, module_id, user_id=user.id)
    return ClearedTopics(deleted=deleted)
