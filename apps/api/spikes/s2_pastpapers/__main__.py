"""Spike S2: past-paper parsing accuracy (ADR 0032). Local only, never in CI.

    cd apps/api
    uv run python -m spikes.s2_pastpapers privacy cos330    # no AI: the submission check
    uv run python -m spikes.s2_pastpapers check-key cos330  # no AI: sums and topic names
    uv run python -m spikes.s2_pastpapers run cos330 [--steps transcribe seg-a seg-b c1 c2]
    uv run python -m spikes.s2_pastpapers score cos330      # writes results/cos330.json

``run`` makes real free-tier calls; see run.py. Course text only goes to ``.local/``.
"""

import argparse
import asyncio
import sys
from typing import TextIO

from sqlalchemy import select

from app.models import Material, MaterialPage, Module, Topic
from evals.common import dev_session
from spikes.s2_pastpapers.key import Key, check_key, load_key
from spikes.s2_pastpapers.privacy import is_submission, read_local_privacy, submission_hashes
from spikes.s2_pastpapers.run import SEGMENTATIONS, STEPS, run
from spikes.s2_pastpapers.score import score
from spikes.s2_pastpapers.text import needs_transcription


async def privacy(key: Key, out: TextIO) -> int:
    """Counts only: never a name, a file name or a value."""
    local = read_local_privacy()
    hashes = submission_hashes(local)
    async with dev_session() as session:
        rows = (
            await session.execute(
                select(Material.title, Material.original_filename, Material.sha256)
                .join(Module, Module.id == Material.module_id)
                .where(Module.code == key.module, Material.kind.in_(("past_paper", "test")))
            )
        ).all()
    matches = sum(
        is_submission(title, local.submission_pattern)
        or is_submission(filename, local.submission_pattern)
        or sha in hashes
        for title, filename, sha in rows
    )
    print(
        f"Past papers and tests: {len(rows)}; matching the submission pattern: {matches}", file=out
    )
    print(f"Excluded entirely (marked scripts): {len(key.excluded_titles)}", file=out)
    for paper in key.papers:
        print(f"  {paper.label}: {len(paper.excluded_pages)} pages excluded", file=out)
    return 1 if matches else 0


async def tree_names(key: Key) -> tuple[set[str], set[str]]:
    async with dev_session() as session:
        topics = list(
            await session.scalars(
                select(Topic)
                .join(Module, Module.id == Topic.module_id)
                .where(Module.code == key.module)
            )
        )
    return {t.name for t in topics if t.parent_id is None}, {
        t.name for t in topics if t.parent_id is not None
    }


async def pages_to_transcribe(key: Key) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    async with dev_session() as session:
        for paper in key.papers:
            rows = await session.execute(
                select(MaterialPage.page_number, MaterialPage.is_scanned, MaterialPage.char_count)
                .join(Material, Material.id == MaterialPage.material_id)
                .join(Module, Module.id == Material.module_id)
                .where(Module.code == key.module, Material.title == paper.title)
                .order_by(MaterialPage.page_number)
            )
            out[paper.label] = [
                n
                for n, scanned, chars in rows
                if n not in paper.excluded_pages and needs_transcription(scanned, chars)
            ]
    return out


async def main_async(args: argparse.Namespace, out: TextIO) -> int:
    key = load_key(args.name)
    if args.command == "privacy":
        return await privacy(key, out)
    if args.command == "check-key":
        chapters, subtopics = await tree_names(key)
        problems = check_key(key, chapters, subtopics)
        for paper in key.papers:
            total = "none printed" if paper.printed_total is None else f"{paper.printed_total:g}"
            print(
                f"{paper.label}: {len(paper.parts)} parts, {paper.marks_sum:g} marks ({total})",
                file=out,
            )
        print("\n".join(problems) or "No problems.", file=out)
        return 1 if problems else 0
    if args.command == "run":
        if await privacy(key, out):
            print("A submission matched: stopping before any AI call.", file=out)
            return 1
        await run(key, args.steps, out, args.on)
        return 0
    chapters, _ = await tree_names(key)
    score(key, args.name, chapters, await pages_to_transcribe(key), out)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m spikes.s2_pastpapers")
    parser.add_argument("command", choices=("privacy", "check-key", "run", "score"))
    parser.add_argument("name", help="the key's name, e.g. cos330")
    parser.add_argument("--steps", nargs="+", choices=STEPS, default=list(STEPS))
    parser.add_argument(
        "--on",
        nargs="+",
        choices=SEGMENTATIONS,
        default=list(SEGMENTATIONS),
        help="the segmentations c1 and c2 classify",
    )
    return asyncio.run(main_async(parser.parse_args(argv), sys.stdout))


if __name__ == "__main__":
    raise SystemExit(main())
