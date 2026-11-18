"""Retrieval for the tutor: the module's best passages for a question, as labelled sources.

1. The module's hybrid search (``services/search``), all of its fused candidates.
2. A topic boost: chunks linked to the session's current topic or any topic under it
   (``chunk_topics``, which holds the topic's cited pages as well as its similar chunks,
   less the pages the student unlinked) have their fused RRF score multiplied by
   ``boost``. No topic, no boost.
3. Only text from materials with ``allow_ai`` on, through ``app/ai/sources.py``.
4. One source per page (its best chunk), at most 8.
5. The context budget: the lowest-ranked sources are dropped until the rendered blocks
   fit ``max_tokens``. A passage is never cut.
6. Labels S1, S2, … in rank order.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.sources import chunks_for_prompt
from app.models import ChunkTopic, Topic
from app.services.errors import NotFound
from app.services.search.embedding import Embedder
from app.services.search.search import CANDIDATES, search_module
from app.services.tutor.prompts import PromptSource, context_text, estimate_tokens

MAX_SOURCES = 8


@dataclass(frozen=True)
class Source:
    label: str
    chunk_id: uuid.UUID
    material_id: uuid.UUID
    material_title: str
    page_number: int
    page_title: str | None
    text: str
    # The fused RRF score after the boost, and before it.
    score: float
    search_score: float
    boosted: bool
    vector_rank: int | None
    keyword_rank: int | None

    def for_prompt(self) -> PromptSource:
        return PromptSource(self.label, self.material_title, self.page_number, self.text)


@dataclass(frozen=True)
class Retrieval:
    sources: list[Source]
    # Estimated tokens of the sources' rendered blocks (what max_tokens limits).
    context_tokens: int
    # Sources that qualified but were dropped to fit the budget.
    dropped: int


@dataclass(frozen=True)
class _Candidate:
    chunk_id: uuid.UUID
    score: float
    search_score: float
    boosted: bool
    vector_rank: int | None
    keyword_rank: int | None


async def topic_and_subtopics(
    session: AsyncSession, module_id: uuid.UUID, topic_id: uuid.UUID, *, user_id: uuid.UUID
) -> set[uuid.UUID]:
    """The topic and every topic below it. ``NotFound`` unless it's in the user's module."""
    rows = (
        await session.execute(
            select(Topic.id, Topic.parent_id).where(
                Topic.module_id == module_id, Topic.user_id == user_id
            )
        )
    ).all()
    if topic_id not in {row[0] for row in rows}:
        raise NotFound("Topic")
    children: dict[uuid.UUID, list[uuid.UUID]] = {}
    for child, parent in rows:
        if parent is not None:
            children.setdefault(parent, []).append(child)
    found: set[uuid.UUID] = set()
    waiting = [topic_id]
    while waiting:
        current = waiting.pop()
        if current not in found:
            found.add(current)
            waiting.extend(children.get(current, []))
    return found


async def _linked_chunks(
    session: AsyncSession,
    module_id: uuid.UUID,
    topic_ids: set[uuid.UUID],
    chunk_ids: list[uuid.UUID],
    *,
    user_id: uuid.UUID,
) -> set[uuid.UUID]:
    """Which of these chunks are linked to any of these topics."""
    rows = await session.scalars(
        select(ChunkTopic.chunk_id)
        # chunk_topics has no user_id: scoped through its topic.
        .join(Topic, (Topic.id == ChunkTopic.topic_id) & (Topic.module_id == ChunkTopic.module_id))
        .where(
            ChunkTopic.module_id == module_id,
            Topic.user_id == user_id,
            ChunkTopic.topic_id.in_(topic_ids),
            ChunkTopic.chunk_id.in_(chunk_ids),
        )
    )
    return set(rows)


def fit_budget[T](items: list[T], cost: Callable[[list[T]], int], max_tokens: int) -> list[T]:
    """Drop items from the end until ``cost`` of the rest is within ``max_tokens``."""
    kept = list(items)
    while kept and cost(kept) > max_tokens:
        kept.pop()
    return kept


async def retrieve(
    session: AsyncSession,
    module_id: uuid.UUID,
    question: str,
    *,
    user_id: uuid.UUID,
    embedder: Embedder,
    topic_id: uuid.UUID | None,
    boost: float,
    max_tokens: int,
) -> Retrieval:
    """The question's sources in the user's module, labelled S1… in rank order.

    ``NotFound`` if the module (or the topic) isn't the user's or isn't in that module.
    """
    found = await search_module(
        session, module_id, question, user_id=user_id, embedder=embedder, limit=2 * CANDIDATES
    )
    topics = (
        await topic_and_subtopics(session, module_id, topic_id, user_id=user_id)
        if topic_id is not None
        else set()
    )
    hit_ids = [hit.chunk_id for hit in found.hits]
    linked = (
        await _linked_chunks(session, module_id, topics, hit_ids, user_id=user_id)
        if topics and hit_ids
        else set()
    )

    candidates = [
        _Candidate(
            chunk_id=hit.chunk_id,
            score=hit.score * boost if hit.chunk_id in linked else hit.score,
            search_score=hit.score,
            boosted=hit.chunk_id in linked,
            vector_rank=hit.vector_rank,
            keyword_rank=hit.keyword_rank,
        )
        for hit in found.hits
    ]
    # Stable: equal scores keep the search's order.
    candidates.sort(key=lambda c: c.score, reverse=True)

    # Only chunks of materials with allow_ai on come back, in the order asked for.
    chunks = await chunks_for_prompt(session, [c.chunk_id for c in candidates], user_id=user_id)
    by_id = {c.chunk_id: c for c in candidates}
    pages: set[tuple[uuid.UUID, int]] = set()
    picked: list[Source] = []
    for chunk in chunks:
        page = (chunk.material_id, chunk.page_number)
        if page in pages:
            continue
        pages.add(page)
        candidate = by_id[chunk.chunk_id]
        picked.append(
            Source(
                label="",
                chunk_id=chunk.chunk_id,
                material_id=chunk.material_id,
                material_title=chunk.material_title,
                page_number=chunk.page_number,
                page_title=chunk.page_title,
                text=chunk.text,
                score=candidate.score,
                search_score=candidate.search_score,
                boosted=candidate.boosted,
                vector_rank=candidate.vector_rank,
                keyword_rank=candidate.keyword_rank,
            )
        )
        if len(picked) == MAX_SOURCES:
            break

    def labelled(sources: list[Source]) -> list[Source]:
        return [replace(s, label=f"S{n}") for n, s in enumerate(sources, start=1)]

    def cost(sources: list[Source]) -> int:
        return estimate_tokens(context_text([s.for_prompt() for s in labelled(sources)]))

    kept = labelled(fit_budget(picked, cost, max_tokens))
    return Retrieval(kept, cost(kept), len(picked) - len(kept))
