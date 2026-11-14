"""Hybrid search over one module's chunks (decision 0005).

Two rankings of the module's chunks, fused with reciprocal rank fusion:
- vector: the 20 nearest by cosine distance to the query's embedding (an exact scan);
- keyword: the 20 best ``websearch_to_tsquery`` matches by ``ts_rank_cd``.
"""

import asyncio
import uuid
from collections.abc import Hashable, Sequence
from dataclasses import dataclass

from sqlalchemy import bindparam, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk, Material, MaterialPage
from app.services.academics.modules import get_module
from app.services.search.embedding import Embedder

CANDIDATES = 20
RRF_K = 60
# ts_headline marks matches with these; they're split out before the snippet leaves the API.
# Interlinear annotation characters: they don't occur in extracted course text.
HIGHLIGHT_START = "￹"
HIGHLIGHT_STOP = "￻"
_HEADLINE_OPTIONS = (
    f'StartSel="{HIGHLIGHT_START}", StopSel="{HIGHLIGHT_STOP}", '
    'MaxWords=35, MinWords=15, MaxFragments=2, FragmentDelimiter=" … "'
)


def reciprocal_rank_fusion[K: Hashable](
    rankings: Sequence[Sequence[K]], *, k: int = RRF_K
) -> list[tuple[K, float]]:
    """Fuse ranked lists: each item scores the sum of 1 / (k + rank) (rank from 1), best first.

    Ties keep the order in which items were first seen.
    """
    scores: dict[K, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)


@dataclass(frozen=True)
class SnippetPart:
    text: str
    highlight: bool


def split_highlights(headline: str) -> list[SnippetPart]:
    """Turn ts_headline output into plain and highlighted parts (no markup leaves the API)."""
    parts: list[SnippetPart] = []
    rest = headline
    while rest:
        start = rest.find(HIGHLIGHT_START)
        if start == -1:
            parts.append(SnippetPart(rest, False))
            break
        if start > 0:
            parts.append(SnippetPart(rest[:start], False))
        stop = rest.find(HIGHLIGHT_STOP, start)
        if stop == -1:
            stop = len(rest)
        if stop > start + 1:
            parts.append(SnippetPart(rest[start + 1 : stop], True))
        rest = rest[stop + 1 :]
    return parts


@dataclass(frozen=True)
class SearchHit:
    chunk_id: uuid.UUID
    material_id: uuid.UUID
    material_title: str
    original_filename: str
    page_number: int
    page_title: str | None
    position: int
    text: str
    snippet: list[SnippetPart]
    score: float
    vector_rank: int | None
    keyword_rank: int | None


@dataclass(frozen=True)
class SearchResults:
    hits: list[SearchHit]
    # How many chunks the module has: 0 means nothing is indexed yet.
    indexed_chunks: int


async def search_module(
    session: AsyncSession,
    module_id: uuid.UUID,
    query: str,
    *,
    user_id: uuid.UUID,
    embedder: Embedder,
    limit: int = 8,
) -> SearchResults:
    await get_module(session, module_id, user_id=user_id)
    query = query.strip()
    in_module = (Chunk.user_id == user_id) & (Chunk.module_id == module_id)
    indexed = await session.scalar(select(func.count()).select_from(Chunk).where(in_module)) or 0
    if indexed == 0 or not query:
        return SearchResults([], indexed)

    vector = await asyncio.to_thread(embedder.embed_query, query)
    distance = Chunk.embedding.cosine_distance(vector)
    by_vector = list(
        await session.scalars(
            select(Chunk.id).where(in_module).order_by(distance, Chunk.id).limit(CANDIDATES)
        )
    )
    tsquery = func.websearch_to_tsquery(literal_column("'english'"), bindparam("q", query))
    rank = func.ts_rank_cd(Chunk.tsv, tsquery)
    by_keyword = list(
        await session.scalars(
            select(Chunk.id)
            .where(in_module, Chunk.tsv.bool_op("@@")(tsquery))
            .order_by(rank.desc(), Chunk.id)
            .limit(CANDIDATES)
        )
    )
    fused = reciprocal_rank_fusion([by_vector, by_keyword])[:limit]
    if not fused:
        return SearchResults([], indexed)

    ids = [chunk_id for chunk_id, _ in fused]
    headline = func.ts_headline(
        literal_column("'english'"), Chunk.text, tsquery, bindparam("opts", _HEADLINE_OPTIONS)
    )
    rows = await session.execute(
        select(
            Chunk.id,
            Chunk.material_id,
            Material.title,
            Material.original_filename,
            Chunk.page_number,
            MaterialPage.title,
            Chunk.position,
            Chunk.text,
            headline,
        )
        .join(Material, (Material.id == Chunk.material_id) & (Material.user_id == Chunk.user_id))
        .join(
            MaterialPage,
            (MaterialPage.material_id == Chunk.material_id)
            & (MaterialPage.page_number == Chunk.page_number),
        )
        .where(in_module, Chunk.id.in_(ids))
    )
    found = {row[0]: row for row in rows}
    vector_ranks = {chunk_id: rank for rank, chunk_id in enumerate(by_vector, start=1)}
    keyword_ranks = {chunk_id: rank for rank, chunk_id in enumerate(by_keyword, start=1)}
    hits = [
        SearchHit(
            chunk_id=chunk_id,
            material_id=row[1],
            material_title=row[2],
            original_filename=row[3],
            page_number=row[4],
            page_title=row[5],
            position=row[6],
            text=row[7],
            snippet=split_highlights(row[8]),
            score=score,
            vector_rank=vector_ranks.get(chunk_id),
            keyword_rank=keyword_ranks.get(chunk_id),
        )
        for chunk_id, score in fused
        if (row := found.get(chunk_id)) is not None
    ]
    return SearchResults(hits, indexed)
