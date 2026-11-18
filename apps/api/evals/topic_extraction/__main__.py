"""Topic-extraction eval: ``uv run --directory apps/api python -m evals.topic_extraction cos330``.

Compares the module's current topic tree with the reference in
``evals/topic_extraction/<name>_reference.yaml`` (the student's reviewed tree: names and
parent names only), and measures citation precision: for each material kind, the share of
AI-cited pages (links with method "pages") that fall in the topic's own chapter.

``... python -m evals.topic_extraction cos330 --export`` rewrites the reference from the
dev database (read-only there; it writes only the YAML file).

No AI extraction runs here: this is the yardstick for prompt changes.
"""

import asyncio
import sys
import uuid
from collections import defaultdict
from typing import Any

import yaml
from sqlalchemy import select

from app.models import Chunk, ChunkTopic, Material, Topic
from evals.common import EVALS_DIR, dev_session, find_module, load_config
from evals.metrics import ChapterCounts, ChapterRules, compare_trees, top_level_names

# Reported apart: the Project chat found its citations spill into neighbouring sections.
WATCH = "COS330 Chapter8 Study Notes"


def reference_path(name: str) -> str:
    return f"topic_extraction/{name}_reference.yaml"


async def load_tree(
    module_code: str,
) -> tuple[uuid.UUID, uuid.UUID, list[tuple[uuid.UUID, str, uuid.UUID | None, int]]]:
    async with dev_session() as session:
        module_id, user_id = await find_module(session, module_code)
        rows = (
            await session.execute(
                select(Topic.id, Topic.name, Topic.parent_id, Topic.position).where(
                    Topic.module_id == module_id, Topic.user_id == user_id
                )
            )
        ).all()
    return module_id, user_id, [(r[0], r[1], r[2], r[3]) for r in rows]


def in_tree_order(
    rows: list[tuple[uuid.UUID, str, uuid.UUID | None, int]],
) -> list[dict[str, str | None]]:
    """Depth first, by position, as {name, parent} with the parent's name."""
    names = {tid: tname for tid, tname, _, _ in rows}
    children: dict[uuid.UUID | None, list[tuple[int, str, uuid.UUID]]] = defaultdict(list)
    for tid, tname, parent, position in rows:
        children[parent].append((position, tname, tid))
    out: list[dict[str, str | None]] = []

    def walk(parent: uuid.UUID | None) -> None:
        for _, tname, tid in sorted(children[parent]):
            out.append({"name": tname, "parent": names[parent] if parent else None})
            walk(tid)

    walk(None)
    return out


async def export(name: str) -> int:
    config = load_config(f"{name}.yaml")
    _, _, rows = await load_tree(config["module"])
    topics = in_tree_order(rows)
    header = (
        f"# {config['module']}'s reviewed topic tree: the reference for evals/topic_extraction.\n"
        "# Topic names and parent names only (no course text). Exported read-only from the dev\n"
        f"# database with `python -m evals.topic_extraction {name} --export`.\n"
    )
    body = yaml.safe_dump(
        {"module": config["module"], "topics": topics}, sort_keys=False, allow_unicode=True
    )
    (EVALS_DIR / reference_path(name)).write_text(header + body, encoding="utf-8", newline="\n")
    print(f"Wrote {len(topics)} topics to evals/{reference_path(name)}")
    return 0


async def main(name: str) -> int:
    config = load_config(f"{name}.yaml")
    chapters = ChapterRules.from_config(config)
    reference: list[dict[str, Any]] = load_config(reference_path(name))["topics"]
    module_id, user_id, rows = await load_tree(config["module"])
    current = in_tree_order(rows)

    result = compare_trees(
        [(str(t["name"]), t["parent"]) for t in reference],
        [(str(t["name"]), t["parent"]) for t in current],
    )
    print(f"Topic-extraction eval: {config['module']}")
    print(f"  reference {len(reference)} topics, current {len(current)} topics")
    print(
        f"  matched {len(result.matched)}, missing {len(result.missing)}, "
        f"extra {len(result.extra)}, "
        f"moved (same name, other parent) {len(result.moved)}"
    )
    for label, items in (("missing", result.missing), ("extra", result.extra)):
        for topic, parent in items:
            print(f"    {label}: {topic}" + (f"  (under {parent})" if parent else ""))
    for topic, was, now in result.moved:
        print(f"    moved: {topic}  ({was} -> {now})")

    # --- citation precision ---
    tree = {tid: (tname, parent) for tid, tname, parent, _ in rows}
    topic_chapter = {
        tid: chapters.topic_chapter(root) for tid, root in top_level_names(tree).items()
    }
    async with dev_session() as session:
        cited = (
            await session.execute(
                select(ChunkTopic.topic_id, Material.kind, Material.title, Chunk.page_number)
                .join(
                    Chunk,
                    (Chunk.id == ChunkTopic.chunk_id) & (Chunk.module_id == ChunkTopic.module_id),
                )
                .join(
                    Material,
                    (Material.id == Chunk.material_id) & (Material.user_id == Chunk.user_id),
                )
                .where(
                    ChunkTopic.module_id == module_id,
                    ChunkTopic.method == "pages",
                    Chunk.user_id == user_id,
                )
                .distinct()
            )
        ).all()
    by_kind: dict[str, ChapterCounts] = defaultdict(ChapterCounts)
    watched = ChapterCounts()
    for topic_id, kind, title, _page in cited:
        page_chapter = chapters.material_chapter(title)
        by_kind[kind].add(topic_chapter.get(topic_id), page_chapter)
        if title == WATCH:
            watched.add(topic_chapter.get(topic_id), page_chapter)
    print()
    print("Citation precision (AI-cited pages in the topic's own chapter, one per topic and page):")
    for kind in sorted(by_kind):
        print("  " + precision_line(kind, by_kind[kind]))
    print("  " + precision_line(WATCH, watched))
    print(
        '  ("no chapter": the material has no chapter, e.g. the study guide, so it isn\'t scored)'
    )
    return 0


def precision_line(label: str, counts: ChapterCounts) -> str:
    scored = counts.same + counts.cross
    share = f"{counts.same / scored:.0%}" if scored else "n/a"
    return (
        f"{label:<30} {counts.same:>4} of {scored:>4} in chapter ({share}), "
        f"{counts.cross} outside, {counts.unknown} no chapter"
    )


if __name__ == "__main__":
    args = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    module = args[0] if args else "cos330"
    sys.exit(asyncio.run(export(module) if "--export" in sys.argv else main(module)))
