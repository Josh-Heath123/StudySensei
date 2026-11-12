import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Topic
from app.schemas.academics import TopicCreate, TopicUpdate
from app.services.academics.modules import get_module
from app.services.errors import Invalid, NotFound


@dataclass
class TopicNode:
    topic: Topic
    children: list["TopicNode"] = field(default_factory=list)


async def list_topics(
    session: AsyncSession, module_id: uuid.UUID, *, user_id: uuid.UUID
) -> list[Topic]:
    """All topics in a module, flat, ordered by position then name."""
    await get_module(session, module_id, user_id=user_id)
    result = await session.scalars(
        select(Topic)
        .where(Topic.module_id == module_id, Topic.user_id == user_id)
        .order_by(Topic.position, Topic.name)
    )
    return list(result)


def build_tree(topics: list[Topic]) -> list[TopicNode]:
    """Turn a flat, ordered topic list into root nodes with nested children."""
    nodes = {t.id: TopicNode(t) for t in topics}
    roots: list[TopicNode] = []
    for topic in topics:
        node = nodes[topic.id]
        parent = nodes.get(topic.parent_id) if topic.parent_id else None
        (parent.children if parent else roots).append(node)
    return roots


async def get_topic(session: AsyncSession, topic_id: uuid.UUID, *, user_id: uuid.UUID) -> Topic:
    topic = await session.scalar(
        select(Topic).where(Topic.id == topic_id, Topic.user_id == user_id)
    )
    if topic is None:
        raise NotFound("Topic")
    return topic


async def _check_parent(
    session: AsyncSession, parent_id: uuid.UUID, module_id: uuid.UUID, *, user_id: uuid.UUID
) -> None:
    parent = await get_topic(session, parent_id, user_id=user_id)
    if parent.module_id != module_id:
        raise Invalid("A topic's parent must be in the same module")


async def create_topic(
    session: AsyncSession, module_id: uuid.UUID, data: TopicCreate, *, user_id: uuid.UUID
) -> Topic:
    await get_module(session, module_id, user_id=user_id)
    if data.parent_id is not None:
        await _check_parent(session, data.parent_id, module_id, user_id=user_id)
    topic = Topic(user_id=user_id, module_id=module_id, source="user", **data.model_dump())
    session.add(topic)
    await session.commit()
    return topic


async def update_topic(
    session: AsyncSession, topic_id: uuid.UUID, data: TopicUpdate, *, user_id: uuid.UUID
) -> Topic:
    topic = await get_topic(session, topic_id, user_id=user_id)
    for name, value in data.model_dump(exclude_unset=True).items():
        setattr(topic, name, value)
    # Any user edit makes the topic the user's, so AI re-runs never overwrite it.
    topic.source = "user"
    await session.commit()
    return topic


async def _descendant_ids(
    session: AsyncSession, topic_id: uuid.UUID, *, user_id: uuid.UUID
) -> set[uuid.UUID]:
    tree = (
        select(Topic.id)
        .where(Topic.parent_id == topic_id, Topic.user_id == user_id)
        .cte("descendants", recursive=True)
    )
    tree = tree.union_all(
        select(Topic.id).where(Topic.parent_id == tree.c.id, Topic.user_id == user_id)
    )
    return set(await session.scalars(select(tree.c.id)))


async def move_topic(
    session: AsyncSession,
    topic_id: uuid.UUID,
    *,
    new_parent_id: uuid.UUID | None,
    position: int,
    user_id: uuid.UUID,
) -> Topic:
    """Re-parent a topic (None = make it a root) and set its position among siblings."""
    topic = await get_topic(session, topic_id, user_id=user_id)
    if new_parent_id is not None:
        await _check_parent(session, new_parent_id, topic.module_id, user_id=user_id)
        if new_parent_id == topic.id or new_parent_id in await _descendant_ids(
            session, topic.id, user_id=user_id
        ):
            raise Invalid("A topic can't be moved under itself or one of its subtopics")
    topic.parent_id = new_parent_id
    topic.position = position
    await session.commit()
    return topic


async def delete_topic(session: AsyncSession, topic_id: uuid.UUID, *, user_id: uuid.UUID) -> None:
    """Deletes the topic and its whole subtree (FK cascade)."""
    topic = await get_topic(session, topic_id, user_id=user_id)
    await session.delete(topic)
    await session.commit()
