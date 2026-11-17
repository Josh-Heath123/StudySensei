import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.core.db import SessionDep
from app.schemas.topic_maps import TopicMapStatus
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
