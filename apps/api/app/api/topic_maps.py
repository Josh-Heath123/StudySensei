import uuid
from typing import Annotated

from fastapi import APIRouter, Path, status

from app.api.deps import CurrentUser
from app.core.db import SessionDep
from app.models import Topic
from app.schemas.academics import TopicOut
from app.schemas.topic_maps import (
    ClearedTopics,
    DismissedCount,
    DismissedTopicOut,
    KeptCount,
    LinkedMaterialOut,
    MaterialTopicStatus,
    MergeInto,
    TopicMapStatus,
)
from app.services import topic_maps
from app.services.topic_maps import review

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


# --- Review (decision 0009) ----------------------------------------------------------


@router.post("/topics/{topic_id}/keep", response_model=TopicOut)
async def keep_topic(topic_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> Topic:
    """Confirm an AI topic as it is: it becomes the student's, counted as kept."""
    return await review.keep_topic(session, topic_id, user_id=user.id)


@router.post("/topics/{topic_id}/merge-into", response_model=TopicOut)
async def merge_topic_into(
    topic_id: uuid.UUID, data: MergeInto, session: SessionDep, user: CurrentUser
) -> Topic:
    """Fold this topic into ``target_id``: its subtopics, cited pages and page links move
    there, then it's deleted. Returns the target. 422 for a topic in another module, the
    topic itself, or one of its subtopics."""
    return await review.merge_into(session, topic_id, data.target_id, user_id=user.id)


@router.post("/topics/{topic_id}/dismiss", response_model=DismissedCount)
async def dismiss_topic(
    topic_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> DismissedCount:
    """Delete an AI topic (and its subtopics still marked AI) and remember the names, so a
    merge never adds them again. The student's subtopics move up. 422 if it isn't AI."""
    count = await review.dismiss_topic(session, topic_id, user_id=user.id)
    return DismissedCount(dismissed=count)


@router.post("/modules/{module_id}/topics/keep-all", response_model=KeptCount)
async def keep_all_topics(
    module_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> KeptCount:
    """Confirm every topic still marked AI."""
    return KeptCount(kept=await review.keep_all(session, module_id, user_id=user.id))


@router.get("/modules/{module_id}/dismissed-topics", response_model=list[DismissedTopicOut])
async def dismissed_topics(
    module_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> list[DismissedTopicOut]:
    return await review.dismissed_topics(session, module_id, user_id=user.id)


@router.post("/dismissed-topics/{dismissed_id}/restore", response_model=TopicOut)
async def restore_topic(dismissed_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> Topic:
    """Bring a dismissed topic back (as kept), with its description and cited pages."""
    return await review.restore_topic(session, dismissed_id, user_id=user.id)


@router.get("/topics/{topic_id}/pages", response_model=list[LinkedMaterialOut])
async def topic_pages(
    topic_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> list[LinkedMaterialOut]:
    """The pages linked to a topic, grouped by material: cited by the AI, or similar
    (with the score)."""
    return await review.linked_pages(session, topic_id, user_id=user.id)


@router.delete(
    "/topics/{topic_id}/pages/{material_id}/{page_number}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unlink_topic_page(
    topic_id: uuid.UUID,
    material_id: uuid.UUID,
    page_number: Annotated[int, Path(ge=1)],
    session: SessionDep,
    user: CurrentUser,
) -> None:
    """Unlink a page from a topic. Remembered: relinking never links it again."""
    await review.unlink_page(session, topic_id, material_id, page_number, user_id=user.id)
