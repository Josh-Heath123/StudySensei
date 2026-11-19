import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser
from app.core.db import SessionDep
from app.models import Topic
from app.schemas.academics import (
    TopicCreate,
    TopicMove,
    TopicNodeOut,
    TopicOut,
    TopicUpdate,
    WorkloadOut,
)
from app.services.academics import topics
from app.services.planning.store import topic_workloads
from app.services.planning.workload import Workload
from app.services.topic_maps.linking import linked_page_counts

router = APIRouter(tags=["topics"])


def _to_out(
    node: topics.TopicNode, pages: dict[uuid.UUID, int], loads: dict[uuid.UUID, Workload]
) -> TopicNodeOut:
    load = loads[node.topic.id]
    return TopicNodeOut(
        **TopicOut.model_validate(node.topic).model_dump(),
        linked_pages=pages.get(node.topic.id, 0),
        workload=WorkloadOut(
            minutes=load.minutes,
            source=load.source,
            slide_pages=load.slide_pages,
            text_pages=load.text_pages,
        ),
        children=[_to_out(child, pages, loads) for child in node.children],
    )


@router.get("/modules/{module_id}/topics", response_model=list[TopicNodeOut])
async def get_topic_tree(
    module_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> list[TopicNodeOut]:
    """The module's topics as a nested tree, siblings in position order, each with the
    number of material pages linked to it, its confidence and its workload (the student's
    figure, or estimated from its slides and text pages)."""
    flat = await topics.list_topics(session, module_id, user_id=user.id)
    pages = await linked_page_counts(session, module_id, user_id=user.id)
    loads = await topic_workloads(session, module_id, flat, user_id=user.id)
    return [_to_out(root, pages, loads) for root in topics.build_tree(flat)]


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
