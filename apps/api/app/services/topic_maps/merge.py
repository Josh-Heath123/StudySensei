"""Apply the AI's merged tree to the module's topics (decision 0006).

Existing topics are fixed anchors: this never renames, moves or deletes one. A node
that is an existing topic (by its "E" id, or by the same name anywhere in the module)
only gains cited pages; any other node becomes a new topic with ``source = "ai"``,
appended after its siblings. So re-running only adds topics that aren't there yet.
"""

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Topic, TopicPage
from app.schemas.topic_maps import MergedSubtopic, ModuleTopicMap
from app.services.topic_maps.prompts import MergeRefs

_PUNCTUATION = re.compile(r"[^\w\s]")


def name_key(name: str) -> str:
    """How two topic names are compared: case, spacing and punctuation don't matter."""
    return " ".join(_PUNCTUATION.sub(" ", name.casefold()).split())


@dataclass(frozen=True)
class MergeOutcome:
    created: int
    # Pages cited for topics (new and existing), as (topic, material, page) rows added.
    pages_linked: int


async def apply_merge(
    session: AsyncSession,
    module_id: uuid.UUID,
    tree: ModuleTopicMap,
    refs: MergeRefs,
    *,
    user_id: uuid.UUID,
) -> MergeOutcome:
    """Add the tree's new topics and cited pages. Doesn't commit."""
    existing = list(
        await session.scalars(
            select(Topic).where(Topic.module_id == module_id, Topic.user_id == user_id)
        )
    )
    by_id = {topic.id: topic for topic in existing}
    by_name: dict[str, Topic] = {}
    for topic in existing:
        by_name.setdefault(name_key(topic.name), topic)
    next_position: dict[uuid.UUID | None, int] = {}
    pages: dict[uuid.UUID, set[tuple[uuid.UUID, int]]] = {}
    created = 0

    async def position_after(parent_id: uuid.UUID | None) -> int:
        if parent_id not in next_position:
            same_parent = (
                Topic.parent_id.is_(None) if parent_id is None else Topic.parent_id == parent_id
            )
            highest = await session.scalar(
                select(func.max(Topic.position)).where(
                    Topic.module_id == module_id, Topic.user_id == user_id, same_parent
                )
            )
            next_position[parent_id] = -1 if highest is None else highest
        next_position[parent_id] += 1
        return next_position[parent_id]

    async def place(node: MergedSubtopic, parent: Topic | None) -> Topic | None:
        nonlocal created
        anchor_id = refs.existing.get(node.existing) if node.existing else None
        if node.existing and anchor_id is not None and anchor_id not in by_id:
            return None  # an anchor deleted since the prompt was built: leave it gone
        topic = by_id.get(anchor_id) if anchor_id else None
        topic = topic or by_name.get(name_key(node.name))
        if topic is None:
            parent_id = parent.id if parent else None
            topic = Topic(
                id=uuid.uuid4(),
                user_id=user_id,
                module_id=module_id,
                parent_id=parent_id,
                name=node.name,
                description=node.description,
                position=await position_after(parent_id),
                source="ai",
            )
            session.add(topic)
            by_id[topic.id] = topic
            by_name[name_key(topic.name)] = topic
            created += 1
        for ref in node.sources:
            if ref in refs.proposals:
                material_id, cited = refs.proposals[ref]
                pages.setdefault(topic.id, set()).update((material_id, n) for n in cited)
        return topic

    for top in tree.topics:
        parent = await place(top, None)
        if parent is None:
            continue
        for sub in top.subtopics:
            if sub.existing is None and name_key(sub.name) == name_key(parent.name):
                continue  # a subtopic repeating its parent
            await place(sub, parent)

    await session.flush()
    rows = [
        {
            "user_id": user_id,
            "module_id": module_id,
            "topic_id": topic_id,
            "material_id": material_id,
            "page_number": page,
        }
        for topic_id, cited in pages.items()
        for material_id, page in sorted(cited)
        if page >= 1
    ]
    if rows:
        await session.execute(
            insert(TopicPage).values(rows).on_conflict_do_nothing(constraint="uq_topic_pages")
        )
    return MergeOutcome(created=created, pages_linked=len(rows))
