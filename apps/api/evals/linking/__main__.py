"""Linking eval: ``uv run --directory apps/api python -m evals.linking cos330``.

1. A report on the module's current similarity links: how many, how many on near-empty
   pages, and how many are in the topic's own chapter (``evals/<name>.yaml`` maps
   chapters). A link is one (topic, page); a page also linked by citation counts as cited.
   Subtopics and the top-level chapter topics are reported apart: a chapter topic's links
   are broad by design, and the 18 Nov baseline counts subtopics.
2. A sweep over the subtopics: each is re-scored against every chunk with the local
   embedder, the way ``app/services/topic_maps/linking.py`` does (no AI), and each rule's
   links are counted.

Cross-chapter isn't always wrong (IDS ↔ IPS is real), so it's a proxy for noise. Read only.
"""

import asyncio
import sys
import uuid
from collections import defaultdict

import numpy as np
from sqlalchemy import select

from app.core.config import get_settings
from app.models import (
    Chunk,
    ChunkTopic,
    Material,
    MaterialPage,
    Topic,
    TopicPage,
    TopicUnlink,
)
from app.services.search.embedding import get_embedder
from app.services.topic_maps.linking import topic_text
from evals.common import dev_session, find_module, load_config
from evals.metrics import (
    ChapterCounts,
    ChapterRules,
    ChunkScore,
    LinkRule,
    Page,
    similarity_pages,
    top_level_names,
)

BASE_THRESHOLD, BASE_CAP = 0.63, 12
THRESHOLDS = [round(0.63 + 0.01 * i, 2) for i in range(18)]  # 0.63 … 0.80
DELTAS = [0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10]
CAPS = [6, 8, 12]
# Aim: drop most cross-chapter links, keep at least this share of the same-chapter ones.
KEEP_SAME = 0.85


def rules() -> list[tuple[str, LinkRule]]:
    found = [("global", LinkRule(t, BASE_CAP)) for t in THRESHOLDS]
    found += [("relative", LinkRule(BASE_THRESHOLD, BASE_CAP, d)) for d in DELTAS]
    found += [("cap", LinkRule(BASE_THRESHOLD, c)) for c in CAPS]
    # The best global thresholds with a smaller cap, and δ with a smaller cap.
    found += [("global+cap", LinkRule(t, 8)) for t in (0.74, 0.76, 0.78)]
    found += [("relative+cap", LinkRule(BASE_THRESHOLD, 8, d)) for d in (0.04, 0.06, 0.08)]
    return found


async def main(name: str) -> int:
    chapters_config = load_config(f"{name}.yaml")
    chapters = ChapterRules.from_config(chapters_config)
    min_chars = get_settings().topic_link_min_page_chars
    embedder = await asyncio.to_thread(get_embedder)

    async with dev_session() as session:
        module_id, user_id = await find_module(session, chapters_config["module"])
        topic_rows = (
            await session.execute(
                select(Topic.id, Topic.name, Topic.description, Topic.parent_id).where(
                    Topic.module_id == module_id, Topic.user_id == user_id
                )
            )
        ).all()
        chunk_rows = (
            await session.execute(
                select(
                    Chunk.id,
                    Material.title,
                    Chunk.page_number,
                    Chunk.embedding,
                    MaterialPage.char_count,
                )
                .join(
                    Material,
                    (Material.id == Chunk.material_id) & (Material.user_id == Chunk.user_id),
                )
                .join(
                    MaterialPage,
                    (MaterialPage.material_id == Chunk.material_id)
                    & (MaterialPage.page_number == Chunk.page_number),
                )
                .where(Chunk.module_id == module_id, Chunk.user_id == user_id)
                .order_by(Chunk.id)
            )
        ).all()
        page_title = select(Material.id, Material.title).where(Material.module_id == module_id)
        titles = {mid: title for mid, title in (await session.execute(page_title)).all()}
        cited: dict[uuid.UUID, set[Page]] = defaultdict(set)
        for topic_id, material_id, page in await session.execute(
            select(TopicPage.topic_id, TopicPage.material_id, TopicPage.page_number).where(
                TopicPage.module_id == module_id, TopicPage.user_id == user_id
            )
        ):
            cited[topic_id].add((titles[material_id], page))
        unlinked: dict[uuid.UUID, set[Page]] = defaultdict(set)
        for topic_id, material_id, page in await session.execute(
            select(TopicUnlink.topic_id, TopicUnlink.material_id, TopicUnlink.page_number).where(
                TopicUnlink.module_id == module_id, TopicUnlink.user_id == user_id
            )
        ):
            unlinked[topic_id].add((titles[material_id], page))
        link_rows = (
            await session.execute(
                select(
                    ChunkTopic.topic_id, ChunkTopic.chunk_id, ChunkTopic.method, ChunkTopic.score
                ).where(ChunkTopic.module_id == module_id)
            )
        ).all()

    tree = {tid: (tname, parent) for tid, tname, _, parent in topic_rows}
    roots = top_level_names(tree)
    topic_chapter = {tid: chapters.topic_chapter(root) for tid, root in roots.items()}
    chunk_page = {cid: (title, page) for cid, title, page, _, _ in chunk_rows}
    page_chars = {(title, page): chars for _, title, page, _, chars in chunk_rows}

    # --- 1. the current links ---
    methods: dict[tuple[uuid.UUID, Page], set[str]] = defaultdict(set)
    scores: dict[tuple[uuid.UUID, Page], float] = {}
    for topic_id, chunk_id, method, score in link_rows:
        key = (topic_id, chunk_page[chunk_id])
        methods[key].add(method)
        if method == "similarity":
            scores[key] = max(scores.get(key, -1.0), score)
    subtopics = {tid for tid, (_, parent) in tree.items() if parent is not None}
    print(
        f"Linking eval: {chapters_config['module']}, {len(topic_rows)} topics "
        f"({len(subtopics)} subtopics), {len(chunk_rows)} chunks"
    )
    print()
    print("Current links (one per topic and page):")
    similarity: list[tuple[uuid.UUID, Page]] = []
    for label, wanted in (("subtopics", True), ("chapter topics (top level)", False)):
        mine = {key: found for key, found in methods.items() if (key[0] in subtopics) == wanted}
        sim = [key for key, found in mine.items() if found == {"similarity"}]
        if wanted:
            similarity = sim
        counts = ChapterCounts()
        for topic_id, linked in sim:
            counts.add(topic_chapter[topic_id], chapters.material_chapter(linked[0]))
        near_empty = sum(1 for _, linked in sim if page_chars.get(linked, 0) < min_chars)
        sim_scores = [scores[key] for key in sim]
        cited_count = sum(1 for found in mine.values() if "pages" in found)
        print(
            f"  {label}: {cited_count} cited, {len(sim)} similarity"
            + (f" (scores {min(sim_scores):.2f}-{max(sim_scores):.2f})" if sim_scores else "")
        )
        print(f"    similarity on pages under {min_chars} characters: {near_empty}")
        print(
            f"    similarity same chapter {counts.same}, cross-chapter {counts.cross}, "
            f"no chapter (study guide) {counts.unknown}"
        )

    # --- 2. the sweep ---
    texts = [topic_text(tname, description) for _, tname, description, _ in topic_rows]
    queries = np.array(await asyncio.to_thread(lambda: [embedder.embed_query(t) for t in texts]))
    vectors = np.array([np.asarray(embedding, dtype=float) for _, _, _, embedding, _ in chunk_rows])
    queries /= np.linalg.norm(queries, axis=1, keepdims=True)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    matrix = queries @ vectors.T
    pages = [(title, page) for _, title, page, _, _ in chunk_rows]
    eligible = [page_chars[page] >= min_chars for page in pages]

    per_topic: list[tuple[uuid.UUID, list[ChunkScore], float | None]] = []
    for row, (topic_id, *_rest) in enumerate(topic_rows):
        if topic_id not in subtopics:
            continue
        candidates = [
            ChunkScore(page[0], page[1], float(matrix[row, col]))
            for col, page in enumerate(pages)
            if eligible[col] and page not in unlinked[topic_id]
        ]
        on_cited = [
            float(matrix[row, col]) for col, page in enumerate(pages) if page in cited[topic_id]
        ]
        per_topic.append((topic_id, candidates, max(on_cited) if on_cited else None))
    without_citations = sum(1 for _, _, best in per_topic if best is None)

    def count(rule: LinkRule) -> ChapterCounts:
        counts = ChapterCounts()
        for topic_id, candidates, best in per_topic:
            for page in similarity_pages(candidates, rule, cited=cited[topic_id], best_cited=best):
                counts.add(topic_chapter[topic_id], chapters.material_chapter(page[0]))
        return counts

    base = count(LinkRule(BASE_THRESHOLD, BASE_CAP))
    print()
    print(
        f"Sweep over the {len(per_topic)} subtopics (re-scored locally; {without_citations} "
        "have no cited pages, so the relative rule leaves them at the threshold):"
    )
    print(
        f"  recomputed current rule: {base.total} links ({base.same} same, {base.cross} cross, "
        f"{base.unknown} no chapter), stored {len(similarity)}"
    )
    columns = ("links", "same", "cross", "none")
    print(f"  {'rule':<62} " + " ".join(f"{c:>5}" for c in columns) + "  same kept  cross kept")
    best: tuple[float, str] | None = None
    for kind, rule in rules():
        counts = count(rule)
        kept_same = counts.same / base.same if base.same else 0.0
        kept_cross = counts.cross / base.cross if base.cross else 0.0
        mark = ""
        if kept_same >= KEEP_SAME:
            mark = " *"
            if best is None or kept_cross < best[0]:
                best = (kept_cross, f"{kind}: {rule.label}")
        values = (counts.total, counts.same, counts.cross, counts.unknown)
        print(
            f"  {kind + ': ' + rule.label:<62} "
            + " ".join(f"{v:>5}" for v in values)
            + f"  {kept_same:>9.0%} {kept_cross:>11.0%}{mark}"
        )
    print(f"  * keeps at least {KEEP_SAME:.0%} of the same-chapter links")
    if best is not None:
        print(
            f"Fewest cross-chapter links among *: {best[1]} ({best[0]:.0%} of cross-chapter kept)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "cos330")))
