"""Retrieval eval: ``uv run --directory apps/api python -m evals.search cos330 --retrieval``.

Runs each query in ``evals/search/<name>.yaml`` through the tutor's ``retrieve`` (the real
local embedder, no AI), first with no topic, then with the query's topic at each boost in
``BOOSTS``. For each run it reports whether an acceptable page is among the sources (8 at
most), its rank (S1 = 1), and the estimated tokens of the built context.

A boost has a cost when the student asks about something outside the session's topic, so
each boost is run once more with a topic from another chapter: query n gets query n+7's
topic (wrapping), which is in a different chapter for all 15.

The dev database's links may predate the current ``TOPIC_LINK_THRESHOLD`` (the eval is
read-only, so it can't relink). The boosted runs are repeated with only the links a
relink would keep: cited pages, and similarity links at or above the threshold.
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import ChunkTopic, Topic
from app.services.search.embedding import Embedder, get_embedder
from app.services.tutor import retrieval
from app.services.tutor.retrieval import MAX_SOURCES, Retrieval, retrieve
from evals.common import dev_session, find_module, load_config
from evals.metrics import Page, first_rank, in_top, mean_reciprocal_rank

BOOSTS = [1.25, 1.5, 2.0, 3.0]
TOP = 3
# Query n's "wrong" topic is query n + SHIFT's (another chapter for every COS330 query).
SHIFT = 7

LinkedChunks = Callable[..., Awaitable[set[uuid.UUID]]]


@dataclass
class Run:
    label: str
    ranks: list[int | None]
    tokens: list[int]
    boosted: list[int]
    # Acceptable pages among the sources, and the source at S1 (material, page).
    acceptable: list[int]
    first: list[Page | None]


def show(rank: int | None) -> str:
    return f"{rank:>2}" if rank is not None else " -"


async def find_topic(
    session: AsyncSession, module_id: uuid.UUID, user_id: uuid.UUID, topic: dict[str, Any]
) -> uuid.UUID:
    """The subtopic with this name under the top-level topic whose name starts "ChN "."""
    parents = {
        topic_id: name
        for topic_id, name in await session.execute(
            select(Topic.id, Topic.name).where(
                Topic.module_id == module_id, Topic.user_id == user_id, Topic.parent_id.is_(None)
            )
        )
    }
    rows = (
        await session.execute(
            select(Topic.id, Topic.parent_id).where(
                Topic.module_id == module_id, Topic.user_id == user_id, Topic.name == topic["name"]
            )
        )
    ).all()
    found = [
        topic_id
        for topic_id, parent in rows
        if parent in parents and parents[parent].startswith(f"{topic['chapter']} ")
    ]
    if len(found) != 1:
        raise SystemExit(f"Expected one topic {topic}, found {len(found)}.")
    return found[0]


def links_at(threshold: float) -> LinkedChunks:
    """``_linked_chunks`` with only the links a relink at ``threshold`` would keep."""

    async def linked(
        session: AsyncSession,
        module_id: uuid.UUID,
        topic_ids: set[uuid.UUID],
        chunk_ids: list[uuid.UUID],
        *,
        user_id: uuid.UUID,
    ) -> set[uuid.UUID]:
        rows = await session.scalars(
            select(ChunkTopic.chunk_id)
            .join(
                Topic,
                (Topic.id == ChunkTopic.topic_id) & (Topic.module_id == ChunkTopic.module_id),
            )
            .where(
                ChunkTopic.module_id == module_id,
                Topic.user_id == user_id,
                ChunkTopic.topic_id.in_(topic_ids),
                ChunkTopic.chunk_id.in_(chunk_ids),
                or_(ChunkTopic.method == "pages", ChunkTopic.score >= threshold),
            )
        )
        return set(rows)

    return linked


async def run_all(
    session: AsyncSession,
    module_id: uuid.UUID,
    user_id: uuid.UUID,
    queries: list[dict[str, Any]],
    topics: list[uuid.UUID],
    embedder: Embedder,
    *,
    label: str,
    boost: float | None,
    max_tokens: int,
) -> Run:
    run = Run(label, [], [], [], [], [])
    for item, topic_id in zip(queries, topics, strict=True):
        found: Retrieval = await retrieve(
            session,
            module_id,
            item["query"],
            user_id=user_id,
            embedder=embedder,
            topic_id=topic_id if boost is not None else None,
            boost=boost or 1.0,
            max_tokens=max_tokens,
        )
        sources: list[Page] = [(s.material_title, s.page_number) for s in found.sources]
        pages = {(p["material"], int(p["page"])) for p in item["pages"]}
        run.ranks.append(first_rank(sources, pages))
        run.tokens.append(found.context_tokens)
        run.boosted.append(sum(1 for s in found.sources if s.boosted))
        run.acceptable.append(sum(1 for page in sources if page in pages))
        run.first.append(sources[0] if sources else None)
    return run


async def main(name: str) -> int:
    config = load_config(f"search/{name}.yaml")
    queries: list[dict[str, Any]] = config["queries"]
    settings = get_settings()
    max_tokens, threshold = settings.tutor_context_max_tokens, settings.topic_link_threshold
    embedder = await asyncio.to_thread(get_embedder)
    stored = retrieval._linked_chunks
    runs: list[Run] = []
    async with dev_session() as session:
        module_id, user_id = await find_module(session, config["module"])
        topics = [await find_topic(session, module_id, user_id, q["topic"]) for q in queries]

        wrong = [topics[(n + SHIFT) % len(topics)] for n in range(len(topics))]

        async def go(label: str, boost: float | None, for_queries: list[uuid.UUID]) -> None:
            runs.append(
                await run_all(
                    session,
                    module_id,
                    user_id,
                    queries,
                    for_queries,
                    embedder,
                    label=label,
                    boost=boost,
                    max_tokens=max_tokens,
                )
            )

        await go("none", None, topics)
        for boost in BOOSTS:
            await go(f"x{boost:g}", boost, topics)
        # The same boosts with the links a relink at the current threshold would keep.
        retrieval._linked_chunks = links_at(threshold)  # type: ignore[assignment]
        try:
            for boost in BOOSTS:
                await go(f"x{boost:g}@{threshold:g}", boost, topics)
            for boost in BOOSTS:
                await go(f"wrong x{boost:g}", boost, wrong)
        finally:
            retrieval._linked_chunks = stored

    print(
        f"Retrieval eval: {config['module']}, {len(queries)} queries, at most {MAX_SOURCES} "
        f"sources, context budget {max_tokens} tokens (estimated at 3.5 characters a token)"
    )
    print("Rank of the first acceptable page among the sources (S1 = 1; - = not in the 8),")
    print("then the context's estimated tokens. Boosted runs use the query's topic;")
    print(f"@{threshold:g} counts only cited links and similarity links >= {threshold:g}.")
    print(f"'wrong' runs use a topic from another chapter, with the @{threshold:g} links.")
    print()
    print(" #  " + " ".join(f"{run.label:>10}" for run in runs) + "  tokens  query")
    for number, item in enumerate(queries, start=1):
        cells = " ".join(f"{show(run.ranks[number - 1]):>10}" for run in runs)
        print(f"{number:>2}  {cells}  {runs[0].tokens[number - 1]:>6}  {item['query']}")
    print()
    total = len(queries)
    misses = [n for n, rank in enumerate(runs[0].ranks) if rank != 1]
    if misses:
        print("S1 when it isn't an acceptable page:")
        for n in misses:
            cells = ", ".join(f"{run.label} {run.first[n]}" for run in runs if run.ranks[n] != 1)
            print(f"  {n + 1:>2}: {cells}")
        print()
    print(
        f"{'run':>12}  in 8   top {TOP}  at S1   MRR  acceptable in 8  boosted/query  "
        "tokens mean/max"
    )
    for run in runs:
        found = in_top(run.ranks, MAX_SOURCES)
        print(
            f"{run.label:>12}  {found:>2}/{total}  {in_top(run.ranks, TOP):>2}/{total}  "
            f"{in_top(run.ranks, 1):>2}/{total}  {mean_reciprocal_rank(run.ranks):.3f}  "
            f"{sum(run.acceptable):>15}  "
            f"{sum(run.boosted) / total:>13.1f}  "
            f"{sum(run.tokens) / total:>6.0f}/{max(run.tokens)}"
        )
    return 0
