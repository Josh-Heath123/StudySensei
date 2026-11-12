import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser
from app.core.db import SessionDep
from app.models import Topic
from app.schemas.academics import TopicCreate, TopicMove, TopicNodeOut, TopicOut, TopicUpdate
from app.services.academics import topics

router = APIRouter(tags=["topics"])


def _to_out(node: topics.TopicNode) -> TopicNodeOut:
    return TopicNodeOut(
        **TopicOut.model_validate(node.topic).model_dump(),
        children=[_to_out(child) for child in node.children],
    )


@router.get("/modules/{module_id}/topics", response_model=list[TopicNodeOut])
async def get_topic_tree(
    module_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> list[TopicNodeOut]:
    """The module's topics as a nested tree, siblings in position order."""
    flat = await topics.list_topics(session, module_id, user_id=user.id)
    return [_to_out(root) for root in topics.build_tree(flat)]


@router.post(
    "/modules/{module_id}/topics", response_model=TopicOut, status_code=status.HTTP_201_CREATED
)
async def create_topic(
    module_id: uuid.UUID, data: TopicCreate, session: SessionDep, user: CurrentUser
) -> Topic:
    return await topics.create_topic(session, module_id, data, user_id=user.id)


@router.patch("/topics/{topic_id}", response_model=TopicOut)
async def update_topic(
    topic_id: uuid.UUID, data: TopicUpdate, session: SessionDep, user: CurrentUser
) -> Topic:
    return await topics.update_topic(session, topic_id, data, user_id=user.id)


@router.post("/topics/{topic_id}/move", response_model=TopicOut)
async def move_topic(
    topic_id: uuid.UUID, data: TopicMove, session: SessionDep, user: CurrentUser
) -> Topic:
    return await topics.move_topic(
        session, topic_id, new_parent_id=data.parent_id, position=data.position, user_id=user.id
    )


@router.delete("/topics/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_topic(topic_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> None:
    """Deletes the topic and all its subtopics."""
    await topics.delete_topic(session, topic_id, user_id=user.id)
