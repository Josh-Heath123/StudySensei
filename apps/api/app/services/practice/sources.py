"""A topic's passages for practice generation (ADR 0025).

1. Chunks linked to the topic or any topic under it (``chunk_topics``; ADR 0019: a topic
   covers its subtree), each at its best link score.
2. Only from materials with ``allow_ai`` on and of the learning kinds: never past papers,
   tests, assignments or outlines (the questions are written from what's taught, not from
   assessments). Both are filtered in the query, and the text itself is read through
   ``app/ai/sources.py``, which checks ``allow_ai`` again.
3. Best link score first, until the rendered blocks reach ``max_tokens``. A passage is never
   cut: the first that doesn't fit ends the list.
4. Labels S1, S2, … in that order, rendered by the tutor's ``context_text`` (each passage in
   its own ``<material>`` tag, marked untrusted by the system prompt).
"""

import math
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.sources import chunks_for_prompt
from app.models import Chunk, ChunkTopic, Material, Topic
from app.services.tutor.prompts import (
    CHARS_PER_TOKEN,
    PromptSource,
    context_text,
    estimate_tokens,
    material_block,
)
from app.services.tutor.retrieval import topic_and_subtopics

# The kinds a student learns from. Assessments and outlines are left out.
LEARNING_KINDS = ("slides", "notes", "study_guide", "tutorial", "other")
NO_SOURCES = "No AI-allowed slides or notes are linked to this topic."


@dataclass(frozen=True)
class PracticeSource:
    label: str
    chunk_id: uuid.UUID
    material_id: uuid.UUID
    material_title: str
    page_number: int
    text: str
    # The best score of its links to the topic's subtree.
    score: float

    def for_prompt(self) -> PromptSource:
        return PromptSource(self.label, self.material_title, self.page_number, self.text)


@dataclass(frozen=True)
class TopicSources:
    sources: list[PracticeSource]
    # Estimated tokens of the rendered sources (what max_tokens limits).
    context_tokens: int
    # Eligible passages left out to fit the budget.
    dropped: int


async def ranked_chunks(
    session: AsyncSession, topic: Topic, *, user_id: uuid.UUID, limit: int | None = None
) -> list[tuple[uuid.UUID, float]]:
    """(chunk id, best link score) for the topic's subtree, eligible ones only, best first."""
    topics = await topic_and_subtopics(session, topic.module_id, topic.id, user_id=user_id)
    best = func.max(ChunkTopic.score)
    query = (
        select(ChunkTopic.chunk_id, best)
        # chunk_topics has no user_id: scoped through its topic and its chunk.
        .join(Topic, (Topic.id == ChunkTopic.topic_id) & (Topic.module_id == ChunkTopic.module_id))
        .join(Chunk, (Chunk.id == ChunkTopic.chunk_id) & (Chunk.module_id == ChunkTopic.module_id))
        .join(Material, (Material.id == Chunk.material_id) & (Material.user_id == Chunk.user_id))
        .where(
            ChunkTopic.module_id == topic.module_id,
            ChunkTopic.topic_id.in_(topics),
            Topic.user_id == user_id,
            Chunk.user_id == user_id,
            Material.allow_ai.is_(True),
            Material.kind.in_(LEARNING_KINDS),
        )
        .group_by(ChunkTopic.chunk_id, Chunk.material_id, Chunk.page_number, Chunk.position)
        # Ties in reading order, so the same links always give the same prompt.
        .order_by(best.desc(), Chunk.material_id, Chunk.page_number, Chunk.position)
    )
    if limit is not None:
        query = query.limit(limit)
    return [(chunk_id, float(score)) for chunk_id, score in await session.execute(query)]


async def has_sources(session: AsyncSession, topic: Topic, *, user_id: uuid.UUID) -> bool:
    return bool(await ranked_chunks(session, topic, user_id=user_id, limit=1))


async def topic_sources(
    session: AsyncSession, topic: Topic, *, user_id: uuid.UUID, max_tokens: int
) -> TopicSources:
    """The topic's passages for a prompt, labelled S1… best first, within ``max_tokens``."""
    ranked = await ranked_chunks(session, topic, user_id=user_id)
    scores = dict(ranked)
    chunks = await chunks_for_prompt(session, [chunk_id for chunk_id, _ in ranked], user_id=user_id)
    kept: list[PracticeSource] = []
    chars = 0
    for chunk in chunks:
        source = PracticeSource(
            label=f"S{len(kept) + 1}",
            chunk_id=chunk.chunk_id,
            material_id=chunk.material_id,
            material_title=chunk.material_title,
            page_number=chunk.page_number,
            text=chunk.text,
            score=scores[chunk.chunk_id],
        )
        # context_text joins the blocks with a blank line.
        added = len(material_block(source.for_prompt())) + (2 if kept else 0)
        if math.ceil((chars + added) / CHARS_PER_TOKEN) > max_tokens:
            break
        kept.append(source)
        chars += added
    tokens = estimate_tokens(context_text([s.for_prompt() for s in kept])) if kept else 0
    return TopicSources(kept, tokens, len(chunks) - len(kept))
