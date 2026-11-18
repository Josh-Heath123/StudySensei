"""Link chunks to topics, with no AI calls (decision 0006).

- ``pages``: chunks on the pages the merge cited for a topic (``topic_pages``).
- ``similarity``: the topic's "name: description" embedded with the local model as a
  query, and the module's most similar chunks at or above the threshold. Chunks on a
  page with less than ``min_page_chars`` of extracted text are never candidates: title
  slides, "Chapter N" dividers and caption-only slides score high against everything
  without teaching anything. A cited page is linked whatever its length (the viewer
  shows the figure).

The module's links are rebuilt from scratch each time, so they always match the current
topics and chunks. A chunk linked both ways keeps ``pages``. Pages the student unlinked
from a topic (``topic_unlinks``) are never linked to it again (decision 0009).
"""

import asyncio
import uuid
from collections.abc import Sequence

from sqlalchemy import ColumnElement, Float, String, Uuid, delete, exists, func, literal, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.models import Chunk, ChunkTopic, MaterialPage, Topic, TopicPage, TopicUnlink
from app.services.search.embedding import Embedder


def _unlinked(
    topic_id: "ColumnElement[uuid.UUID] | InstrumentedAttribute[uuid.UUID] | uuid.UUID",
) -> ColumnElement[bool]:
    """The chunk's page was unlinked from the topic by the student."""
    return exists().where(
        TopicUnlink.topic_id == topic_id,
        TopicUnlink.material_id == Chunk.material_id,
        TopicUnlink.page_number == Chunk.page_number,
    )


def _near_empty(min_page_chars: int) -> ColumnElement[bool]:
    """The chunk's page has less than ``min_page_chars`` of extracted text."""
    return exists().where(
        MaterialPage.user_id == Chunk.user_id,
        MaterialPage.material_id == Chunk.material_id,
        MaterialPage.page_number == Chunk.page_number,
        MaterialPage.char_count < min_page_chars,
    )


def topic_text(name: str, description: str | None) -> str:
    return f"{name}: {description}" if description and description.strip() else name


async def link_module(
    session: AsyncSession,
    module_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
    embedder: Embedder,
    threshold: float,
    max_chunks: int,
    min_page_chars: int,
) -> int:
    """Rebuild the module's chunk links. Returns how many there are. Doesn't commit."""
    topics = (
        await session.execute(
            select(Topic.id, Topic.name, Topic.description)
            .where(Topic.module_id == module_id, Topic.user_id == user_id)
            .order_by(Topic.id)
        )
    ).all()
    # Scoped through the topics: chunk_topics has no user_id.
    await session.execute(
        delete(ChunkTopic).where(
            ChunkTopic.module_id == module_id,
            ChunkTopic.topic_id.in_(
                select(Topic.id).where(Topic.module_id == module_id, Topic.user_id == user_id)
            ),
        )
    )
    if not topics:
        return 0

    await session.execute(
        insert(ChunkTopic)
        .from_select(
            # One id per row from Postgres (a Python default would give every row the same).
            ["id", "module_id", "chunk_id", "topic_id", "score", "method"],
            select(
                func.gen_random_uuid(),
                literal(module_id, type_=Uuid),
                Chunk.id,
                TopicPage.topic_id,
                literal(1.0, type_=Float),
                literal("pages", type_=String),
            )
            .join(
                Chunk,
                (Chunk.material_id == TopicPage.material_id)
                & (Chunk.page_number == TopicPage.page_number)
                & (Chunk.user_id == TopicPage.user_id),
            )
            .where(
                TopicPage.user_id == user_id,
                TopicPage.module_id == module_id,
                ~_unlinked(TopicPage.topic_id),
            ),
        )
        .on_conflict_do_nothing(constraint="uq_chunk_topics")
    )

    texts = [topic_text(name, description) for _, name, description in topics]
    vectors: Sequence[list[float]] = await asyncio.to_thread(
        lambda: [embedder.embed_query(text) for text in texts]
    )
    for (topic_id, _, _), vector in zip(topics, vectors, strict=True):
        distance = Chunk.embedding.cosine_distance(vector)
        nearest = (
            await session.execute(
                select(Chunk.id, (1 - distance).label("score"))
                .where(
                    Chunk.user_id == user_id,
                    Chunk.module_id == module_id,
                    ~_unlinked(topic_id),
                    ~_near_empty(min_page_chars),
                )
                .order_by(distance)
                .limit(max_chunks)
            )
        ).all()
        rows = [
            {
                "module_id": module_id,
                "chunk_id": chunk_id,
                "topic_id": topic_id,
                "score": max(-1.0, min(1.0, float(score))),
                "method": "similarity",
            }
            for chunk_id, score in nearest
            if score >= threshold
        ]
        if rows:
            await session.execute(
                insert(ChunkTopic).values(rows).on_conflict_do_nothing(constraint="uq_chunk_topics")
            )
    count = await session.scalar(
        select(func.count()).select_from(ChunkTopic).where(ChunkTopic.module_id == module_id)
    )
    return int(count or 0)


async def linked_page_counts(
    session: AsyncSession, module_id: uuid.UUID, *, user_id: uuid.UUID
) -> dict[uuid.UUID, int]:
    """Distinct pages linked to each of the module's topics."""
    page = func.concat(Chunk.material_id, literal(":"), Chunk.page_number)
    rows = await session.execute(
        select(ChunkTopic.topic_id, func.count(func.distinct(page)))
        .join(Chunk, (Chunk.id == ChunkTopic.chunk_id) & (Chunk.module_id == ChunkTopic.module_id))
        .join(Topic, (Topic.id == ChunkTopic.topic_id) & (Topic.module_id == ChunkTopic.module_id))
        .where(
            ChunkTopic.module_id == module_id,
            Topic.user_id == user_id,
            Chunk.user_id == user_id,
        )
        .group_by(ChunkTopic.topic_id)
    )
    return {topic_id: int(count) for topic_id, count in rows}
