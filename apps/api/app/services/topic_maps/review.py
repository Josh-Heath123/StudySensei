"""Reviewing the AI's topics (decision 0009): keep, rename, merge into, dismiss, restore,
and the pages linked to a topic.

Whatever the student does to an AI topic makes it theirs (``source = "user"``), and the
first action is recorded in ``topic_reviews``. Later actions update that record (a kept
topic later renamed counts as renamed). The record outlives a merged or dismissed topic:
the merge reads it so a dismissed name never comes back and an old AI name adds to the
topic that carries it now.
"""

import uuid
from typing import Any

from sqlalchemy import Uuid, delete, func, literal, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.queue import enqueue_replan
from app.models import (
    Chunk,
    ChunkTopic,
    Material,
    MaterialPage,
    Topic,
    TopicPage,
    TopicReview,
    TopicUnlink,
)
from app.schemas.topic_maps import (
    DismissedTopicOut,
    LinkedMaterialOut,
    LinkedPageOut,
)
from app.services.academics.modules import get_module
from app.services.errors import Invalid, NotFound
from app.services.topic_maps import queue_linking, remove_topics
from app.services.topic_maps.merge import name_key

LABEL_CHARS = 120
# A later outcome replaces an earlier one, except that "renamed" isn't undone by "kept".
_RANK = {"kept": 0, "renamed": 1, "merged": 2, "dismissed": 2}


async def _topic(session: AsyncSession, topic_id: uuid.UUID, *, user_id: uuid.UUID) -> Topic:
    topic = await session.scalar(
        select(Topic).where(Topic.id == topic_id, Topic.user_id == user_id)
    )
    if topic is None:
        raise NotFound("Topic")
    return topic


async def _review_of(
    session: AsyncSession, topic: Topic, *, user_id: uuid.UUID
) -> TopicReview | None:
    return await session.scalar(
        select(TopicReview).where(
            TopicReview.user_id == user_id,
            TopicReview.module_id == topic.module_id,
            TopicReview.topic_id == topic.id,
        )
    )


async def note_review(
    session: AsyncSession,
    topic: Topic,
    outcome: str,
    *,
    user_id: uuid.UUID,
    ai_name: str | None = None,
    target_id: uuid.UUID | None = None,
    snapshot: dict[str, Any] | None = None,
) -> None:
    """Record what the student did with ``topic``, if it came from the AI (it's still marked
    AI, or it was reviewed before). ``ai_name`` is its name before this action. Makes the
    topic the student's. Doesn't commit."""
    review = await _review_of(session, topic, user_id=user_id)
    if review is None and topic.source != "ai":
        return  # the student's own topic: nothing to review
    topic.source = "user"
    if review is None:
        name = ai_name or topic.name
        session.add(
            TopicReview(
                user_id=user_id,
                module_id=topic.module_id,
                topic_id=topic.id,
                target_id=target_id,
                name=name[:200],
                name_key=name_key(name)[:200],
                outcome=outcome,
                snapshot=snapshot,
            )
        )
        return
    if _RANK[outcome] >= _RANK[review.outcome]:
        review.outcome = outcome
    review.target_id = target_id
    review.snapshot = snapshot


async def record_edit(
    session: AsyncSession, topic: Topic, *, old_name: str, user_id: uuid.UUID
) -> None:
    """An edit through the ordinary topic endpoints (rename, describe, move): an AI topic
    counts as renamed if its name changed, else kept. Doesn't commit."""
    renamed = name_key(old_name) != name_key(topic.name)
    await note_review(
        session,
        topic,
        "renamed" if renamed else "kept",
        user_id=user_id,
        ai_name=old_name,
        target_id=topic.id,
    )


async def keep_topic(session: AsyncSession, topic_id: uuid.UUID, *, user_id: uuid.UUID) -> Topic:
    """Confirm an AI topic as it is."""
    topic = await _topic(session, topic_id, user_id=user_id)
    await note_review(session, topic, "kept", user_id=user_id, target_id=topic.id)
    await session.commit()
    return topic


async def keep_all(session: AsyncSession, module_id: uuid.UUID, *, user_id: uuid.UUID) -> int:
    """Confirm every topic in the module still marked AI. Returns how many."""
    await get_module(session, module_id, user_id=user_id)
    topics = list(
        await session.scalars(
            select(Topic).where(
                Topic.module_id == module_id, Topic.user_id == user_id, Topic.source == "ai"
            )
        )
    )
    for topic in topics:
        await note_review(session, topic, "kept", user_id=user_id, target_id=topic.id)
    await session.commit()
    return len(topics)


async def _module_topics(
    session: AsyncSession, module_id: uuid.UUID, *, user_id: uuid.UUID
) -> list[Topic]:
    return list(
        await session.scalars(
            select(Topic)
            .where(Topic.module_id == module_id, Topic.user_id == user_id)
            .order_by(Topic.position, Topic.name)
        )
    )


def _subtree(topics: list[Topic], root: uuid.UUID) -> list[Topic]:
    """``root``'s descendants (not ``root`` itself), parents before children."""
    children: dict[uuid.UUID | None, list[Topic]] = {}
    for topic in topics:
        children.setdefault(topic.parent_id, []).append(topic)
    found: list[Topic] = []
    stack = list(reversed(children.get(root, [])))
    while stack:
        topic = stack.pop()
        found.append(topic)
        stack.extend(reversed(children.get(topic.id, [])))
    return found


async def merge_into(
    session: AsyncSession, topic_id: uuid.UUID, target_id: uuid.UUID, *, user_id: uuid.UUID
) -> Topic:
    """Fold a topic into another: its subtopics, cited pages and page links move to the
    target (after the target's own), then it's deleted. Returns the target."""
    topic = await _topic(session, topic_id, user_id=user_id)
    target = await _topic(session, target_id, user_id=user_id)
    if target.module_id != topic.module_id:
        raise Invalid("A topic can only be merged into a topic in the same module")
    if target.id == topic.id:
        raise Invalid("A topic can't be merged into itself")
    topics = await _module_topics(session, topic.module_id, user_id=user_id)
    if target.id in {t.id for t in _subtree(topics, topic.id)}:
        raise Invalid("A topic can't be merged into one of its own subtopics")

    module_id = topic.module_id
    after = 1 + max((t.position for t in topics if t.parent_id == target.id), default=-1)
    for offset, child in enumerate(t for t in topics if t.parent_id == topic.id):
        child.parent_id = target.id
        child.position = after + offset
    await session.flush()
    await session.execute(
        insert(TopicPage)
        .from_select(
            ["id", "user_id", "module_id", "topic_id", "material_id", "page_number"],
            select(
                func.gen_random_uuid(),
                TopicPage.user_id,
                TopicPage.module_id,
                literal(target.id, type_=Uuid),
                TopicPage.material_id,
                TopicPage.page_number,
            ).where(TopicPage.topic_id == topic.id, TopicPage.user_id == user_id),
        )
        .on_conflict_do_nothing(constraint="uq_topic_pages")
    )
    await session.execute(
        insert(ChunkTopic)
        .from_select(
            ["id", "module_id", "chunk_id", "topic_id", "score", "method"],
            select(
                func.gen_random_uuid(),
                ChunkTopic.module_id,
                ChunkTopic.chunk_id,
                literal(target.id, type_=Uuid),
                ChunkTopic.score,
                ChunkTopic.method,
            ).where(ChunkTopic.topic_id == topic.id, ChunkTopic.module_id == module_id),
        )
        .on_conflict_do_nothing(constraint="uq_chunk_topics")
    )
    # Earlier merges into this topic now point at the target too.
    for alias in await session.scalars(
        select(TopicReview).where(
            TopicReview.user_id == user_id,
            TopicReview.module_id == module_id,
            TopicReview.target_id == topic.id,
            TopicReview.topic_id != topic.id,
        )
    ):
        alias.target_id = target.id
    await note_review(session, topic, "merged", user_id=user_id, target_id=target.id)
    # Choosing it as the home confirms the target too.
    await note_review(session, target, "kept", user_id=user_id, target_id=target.id)
    await session.flush()
    await remove_topics(session, module_id, {topic.id}, user_id=user_id)
    await enqueue_replan(
        session, user_id=user_id, trigger="topic", detail={"module_id": str(module_id)}
    )
    await session.commit()
    return target


async def dismiss_topic(session: AsyncSession, topic_id: uuid.UUID, *, user_id: uuid.UUID) -> int:
    """Delete an AI topic and remember its name, so a merge never adds it again.

    Its subtopics still marked AI are dismissed with it; the student's own (and reviewed)
    subtopics move up to its parent. Returns how many topics were dismissed.
    """
    topic = await _topic(session, topic_id, user_id=user_id)
    if topic.source != "ai":
        raise Invalid("Only AI topics not yet reviewed can be dismissed. Delete it instead.")
    module_id = topic.module_id
    topics = await _module_topics(session, module_id, user_id=user_id)
    doomed = [topic, *(t for t in _subtree(topics, topic.id) if t.source == "ai")]
    ids = [t.id for t in doomed]
    cited: dict[uuid.UUID, list[list[Any]]] = {}
    for owner, material_id, page in await session.execute(
        select(TopicPage.topic_id, TopicPage.material_id, TopicPage.page_number)
        .where(TopicPage.user_id == user_id, TopicPage.topic_id.in_(ids))
        .order_by(TopicPage.material_id, TopicPage.page_number)
    ):
        cited.setdefault(owner, []).append([str(material_id), page])
    for t in doomed:
        snapshot = {
            "description": t.description,
            "parent_id": str(t.parent_id) if t.parent_id else None,
            "pages": cited.get(t.id, []),
        }
        await note_review(session, t, "dismissed", user_id=user_id, snapshot=snapshot)
    await session.flush()
    await remove_topics(session, module_id, set(ids), user_id=user_id)
    await enqueue_replan(
        session, user_id=user_id, trigger="topic", detail={"module_id": str(module_id)}
    )
    await session.commit()
    return len(doomed)


async def dismissed_topics(
    session: AsyncSession, module_id: uuid.UUID, *, user_id: uuid.UUID
) -> list[DismissedTopicOut]:
    """The module's dismissed AI topics, most recent first."""
    await get_module(session, module_id, user_id=user_id)
    rows = await session.scalars(
        select(TopicReview)
        .where(
            TopicReview.user_id == user_id,
            TopicReview.module_id == module_id,
            TopicReview.outcome == "dismissed",
        )
        .order_by(TopicReview.updated_at.desc(), TopicReview.name)
    )
    return [DismissedTopicOut(id=r.id, name=r.name, dismissed_at=r.updated_at) for r in rows]


async def restore_topic(
    session: AsyncSession, review_id: uuid.UUID, *, user_id: uuid.UUID
) -> Topic:
    """Bring a dismissed topic back, as the student's: its name, description and cited
    pages, under its old parent if that's still there (else at the top level). It then
    counts as kept, and its name is no longer blocked."""
    review = await session.scalar(
        select(TopicReview).where(
            TopicReview.id == review_id,
            TopicReview.user_id == user_id,
            TopicReview.outcome == "dismissed",
        )
    )
    if review is None:
        raise NotFound("Dismissed topic")
    module_id = review.module_id
    snapshot = review.snapshot or {}
    topics = await _module_topics(session, module_id, user_id=user_id)
    ids = {t.id for t in topics}
    parent = snapshot.get("parent_id")
    parent_id = uuid.UUID(parent) if parent and uuid.UUID(parent) in ids else None
    topic = Topic(
        id=uuid.uuid4(),
        user_id=user_id,
        module_id=module_id,
        parent_id=parent_id,
        name=review.name,
        description=snapshot.get("description"),
        position=1 + max((t.position for t in topics if t.parent_id == parent_id), default=-1),
        source="user",
    )
    session.add(topic)
    await session.flush()
    pages = [(uuid.UUID(m), int(n)) for m, n in snapshot.get("pages", [])]
    materials = set(
        await session.scalars(
            select(Material.id).where(Material.module_id == module_id, Material.user_id == user_id)
        )
    )
    rows = [
        {
            "user_id": user_id,
            "module_id": module_id,
            "topic_id": topic.id,
            "material_id": material_id,
            "page_number": page,
        }
        for material_id, page in pages
        if material_id in materials and page >= 1
    ]
    if rows:
        await session.execute(
            insert(TopicPage).values(rows).on_conflict_do_nothing(constraint="uq_topic_pages")
        )
    review.outcome, review.topic_id, review.target_id, review.snapshot = (
        "kept",
        topic.id,
        topic.id,
        None,
    )
    await queue_linking(session, module_id, user_id=user_id)
    await enqueue_replan(
        session, user_id=user_id, trigger="topic", detail={"module_id": str(module_id)}
    )
    await session.commit()
    return topic


def _label(title: str | None, text: str) -> str:
    """A page's title, or its first non-empty line, clipped."""
    if title and title.strip():
        line = title.strip()
    else:
        line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    line = " ".join(line.split())
    return line if len(line) <= LABEL_CHARS else line[: LABEL_CHARS - 1].rstrip() + "…"


async def linked_pages(
    session: AsyncSession, topic_id: uuid.UUID, *, user_id: uuid.UUID
) -> list[LinkedMaterialOut]:
    """The pages linked to a topic, grouped by material. A page with a cited chunk is
    "pages"; otherwise it's "similarity" with its best chunk's score."""
    topic = await _topic(session, topic_id, user_id=user_id)
    rows = await session.execute(
        select(
            Chunk.material_id,
            Chunk.page_number,
            func.bool_or(ChunkTopic.method == "pages"),
            func.max(ChunkTopic.score),
        )
        .join(Chunk, (Chunk.id == ChunkTopic.chunk_id) & (Chunk.module_id == ChunkTopic.module_id))
        .where(
            ChunkTopic.topic_id == topic.id,
            ChunkTopic.module_id == topic.module_id,
            Chunk.user_id == user_id,
        )
        .group_by(Chunk.material_id, Chunk.page_number)
    )
    links = {(m, n): (cited, float(score)) for m, n, cited, score in rows}
    if not links:
        return []
    material_ids = {m for m, _ in links}
    materials = (
        await session.execute(
            select(Material.id, Material.title)
            .where(Material.user_id == user_id, Material.id.in_(material_ids))
            .order_by(Material.created_at, Material.title, Material.id)
        )
    ).all()
    labels = {
        (m, n): _label(title, text)
        for m, n, title, text in await session.execute(
            select(
                MaterialPage.material_id,
                MaterialPage.page_number,
                MaterialPage.title,
                MaterialPage.text,
            ).where(MaterialPage.user_id == user_id, MaterialPage.material_id.in_(material_ids))
        )
        if (m, n) in links
    }
    return [
        LinkedMaterialOut(
            material_id=material_id,
            title=title,
            pages=[
                LinkedPageOut(
                    page_number=n,
                    label=labels.get((material_id, n), ""),
                    method="pages" if cited else "similarity",
                    score=None if cited else round(score, 3),
                )
                for (m, n), (cited, score) in sorted(links.items(), key=lambda kv: kv[0][1])
                if m == material_id
            ],
        )
        for material_id, title in materials
    ]


async def unlink_page(
    session: AsyncSession,
    topic_id: uuid.UUID,
    material_id: uuid.UUID,
    page_number: int,
    *,
    user_id: uuid.UUID,
) -> None:
    """Unlink one page from a topic, for good: relinking skips it from now on."""
    topic = await _topic(session, topic_id, user_id=user_id)
    material = await session.scalar(
        select(Material.id).where(
            Material.id == material_id,
            Material.user_id == user_id,
            Material.module_id == topic.module_id,
        )
    )
    if material is None:
        raise NotFound("Material")
    await session.execute(
        insert(TopicUnlink)
        .values(
            user_id=user_id,
            module_id=topic.module_id,
            topic_id=topic.id,
            material_id=material_id,
            page_number=page_number,
        )
        .on_conflict_do_nothing(constraint="uq_topic_unlinks")
    )
    await session.execute(
        delete(TopicPage).where(
            TopicPage.user_id == user_id,
            TopicPage.topic_id == topic.id,
            TopicPage.material_id == material_id,
            TopicPage.page_number == page_number,
        )
    )
    await session.execute(
        delete(ChunkTopic).where(
            ChunkTopic.topic_id == topic.id,
            ChunkTopic.module_id == topic.module_id,
            ChunkTopic.chunk_id.in_(
                select(Chunk.id).where(
                    Chunk.user_id == user_id,
                    Chunk.material_id == material_id,
                    Chunk.page_number == page_number,
                )
            ),
        )
    )
    await enqueue_replan(
        session, user_id=user_id, trigger="topic", detail={"module_id": str(topic.module_id)}
    )
    await session.commit()
