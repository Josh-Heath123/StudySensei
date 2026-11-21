"""Practice eval (ADR 0025). Local only, never in CI. Two steps:

    uv run --directory apps/api python -m evals.practice cos330
    uv run --directory apps/api python -m evals.practice score cos330

**Generate** (real AI calls on the free tier, one per topic plus any repair or fallback):
practice items for each topic in ``practice/<name>.yaml``, through the service the job uses
(``prepare``, ``ask`` and the filter), on a read-only dev-database session with usage kept in
memory: **nothing is stored**. It writes a spot-check sheet,
``evals/practice/.local/spotcheck-<date>.csv`` (gitignored: it holds AI text about the
course), with an empty "answerable" column for a person to fill in with y or n, and the run's
counts beside it (``spotcheck-<date>.json``). Calls are paced like the tutor eval's.

**Score** (no AI calls): reads the newest sheet with at least one mark and writes
``evals/results/practice-<name>.json`` with numbers only: items, grounded % (of the items
the model returned, those citing only the sources they were given), how many are marked,
and answerable % overall and by kind. The roadmap's target: at least 90 % of at least 30
marked items answerable from their cited source.
"""

import argparse
import asyncio
import csv
import json
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from sqlalchemy import func, select

from app.ai.client import LLMClient
from app.ai.errors import AIUnavailable
from app.core.config import get_settings
from app.models import Topic
from app.services.practice.generation import GenerationFailed, ask, keep, prepare
from app.services.tutor.prompts import estimate_tokens
from app.tutor.ask import read_only_sessions
from evals.common import EVALS_DIR, find_module, load_config
from evals.tutor.__main__ import Pacer, TimedUsage

LOCAL = EVALS_DIR / "practice" / ".local"
RESULTS = EVALS_DIR / "results"
COLUMNS = (
    "item",
    "topic",
    "kind",
    "prompt",
    "answer",
    "key_points",
    "cited",
    "answerable",
)
TARGET_SHARE = 0.9
TARGET_MARKED = 30


async def generate(name: str, out: TextIO = sys.stdout) -> int:
    config = load_config(f"practice/{name}.yaml")
    settings = get_settings()
    count = int(config.get("count", 8))
    rows: list[dict[str, str]] = []
    totals: dict[str, Any] = {"topics": [], "requested": 0, "returned": 0, "kept": 0}
    dropped: dict[str, int] = {}
    started = time.monotonic()
    async with read_only_sessions(settings) as sessions:
        usage = TimedUsage(sessions)
        pacer = Pacer(usage, log=out)
        client = LLMClient(settings, usage)
        try:
            async with sessions() as session:
                module_id, user_id = await find_module(session, config["module"])
                for topic_name in config["topics"]:
                    topic = (
                        await session.scalars(
                            select(Topic).where(
                                Topic.module_id == module_id,
                                Topic.user_id == user_id,
                                func.lower(Topic.name) == topic_name.lower(),
                            )
                        )
                    ).one()
                    prepared = await prepare(
                        session,
                        topic,
                        count,
                        user_id=user_id,
                        max_tokens=settings.practice_context_max_tokens,
                    )
                    await pacer.before(sum(estimate_tokens(m.text) for m in prepared.messages))
                    seen = len(usage.rows)
                    try:
                        reply = await ask(client, prepared, user_id=user_id)
                    except (GenerationFailed, AIUnavailable) as exc:
                        print(f"{topic_name}: failed ({exc})", file=out)
                        # Why (what didn't validate, or the provider's status): no course text.
                        for row in usage.rows[seen:]:
                            if row.outcome != "ok" and row.detail:
                                print(
                                    f"  {row.provider}/{row.model} {row.outcome}: {row.detail}",
                                    file=out,
                                )
                        totals["topics"].append({"requested": count, "failed": True})
                        totals["requested"] += count
                        continue
                    filtered = keep(reply.items, prepared, set(prepared.existing_keys))
                    by_label = {s.label: s for s in prepared.sources.sources}
                    for item in filtered.kept:
                        # Distinct pages, in label order (two passages of p7 are one p7).
                        cited = "; ".join(
                            dict.fromkeys(
                                f"{by_label[label].material_title} p{by_label[label].page_number}"
                                for label in item.sources
                            )
                        )
                        rows.append(
                            {
                                "item": str(len(rows) + 1),
                                "topic": topic_name,
                                "kind": item.kind,
                                "prompt": item.prompt,
                                "answer": item.answer,
                                "key_points": " | ".join(item.key_points or []),
                                "cited": cited,
                                "answerable": "",
                            }
                        )
                    for reason, n in filtered.dropped.items():
                        dropped[reason] = dropped.get(reason, 0) + n
                    model = f"{reply.route.provider.name}/{reply.route.model}"
                    totals["topics"].append(
                        {
                            "requested": count,
                            "returned": len(reply.items),
                            "kept": len(filtered.kept),
                            "dropped": filtered.dropped,
                            "model": model,
                            "context_tokens": prepared.sources.context_tokens,
                        }
                    )
                    totals["requested"] += count
                    totals["returned"] += len(reply.items)
                    totals["kept"] += len(filtered.kept)
                    print(
                        f"Topic {len(totals['topics'])}: requested {count}, returned "
                        f"{len(reply.items)}, kept {len(filtered.kept)}, dropped "
                        f"{filtered.dropped or 'none'} ({model})",
                        file=out,
                        flush=True,
                    )
        finally:
            await client.aclose()
    totals["dropped"] = dropped
    totals["input_tokens"] = sum(r.input_tokens for r in usage.rows)
    totals["output_tokens"] = sum(r.output_tokens for r in usage.rows)
    totals["calls"] = len(usage.rows)
    totals["seconds"] = round(time.monotonic() - started, 1)
    totals["paced_seconds"] = pacer.waited

    LOCAL.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d-%H%M")
    sheet = LOCAL / f"spotcheck-{stamp}.csv"
    with sheet.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    sheet.with_suffix(".json").write_text(json.dumps(totals, indent=2), encoding="utf-8")
    print(
        f"\nRequested {totals['requested']} · returned {totals['returned']} · kept "
        f"{totals['kept']} · dropped {dropped or 'none'}\nTokens {totals['input_tokens']} in, "
        f"{totals['output_tokens']} out · {totals['calls']} calls · {totals['seconds']} s "
        f"({totals['paced_seconds']:.0f} s pacing)\nSheet: {sheet}",
        file=out,
    )
    return 0


@dataclass(frozen=True)
class Mark:
    kind: str
    answerable: bool | None


def marks_of(rows: Sequence[dict[str, str]]) -> list[Mark]:
    """Each row's kind and mark: y (yes), n (no), or None (not marked yet)."""
    found = []
    for row in rows:
        value = (row.get("answerable") or "").strip().lower()
        answerable = True if value in ("y", "yes") else False if value in ("n", "no") else None
        found.append(Mark(row.get("kind", ""), answerable))
    return found


def share(marks: Sequence[Mark]) -> float | None:
    marked = [m for m in marks if m.answerable is not None]
    if not marked:
        return None
    return round(100 * sum(1 for m in marked if m.answerable) / len(marked), 1)


def score_sheet(rows: Sequence[dict[str, str]], counts: dict[str, Any]) -> dict[str, Any]:
    """Numbers only: items, grounded %, marked, answerable % overall and by kind."""
    marks = marks_of(rows)
    marked = [m for m in marks if m.answerable is not None]
    returned = int(counts.get("returned", 0))
    not_grounded = int((counts.get("dropped") or {}).get("not_grounded", 0))
    overall = share(marks)
    return {
        "items": len(rows),
        "returned": returned,
        "grounded_pct": (
            round(100 * (returned - not_grounded) / returned, 1) if returned else None
        ),
        "dropped": counts.get("dropped", {}),
        "marked": len(marked),
        "answerable_pct": overall,
        "answerable_pct_by_kind": {
            kind: share([m for m in marks if m.kind == kind])
            for kind in sorted({m.kind for m in marks})
        },
        "target": {"answerable_pct": TARGET_SHARE * 100, "marked": TARGET_MARKED},
        "passed": overall is not None
        and len(marked) >= TARGET_MARKED
        and overall >= TARGET_SHARE * 100,
    }


def newest_marked(folder: Path) -> Path | None:
    for sheet in sorted(folder.glob("spotcheck-*.csv"), reverse=True):
        with sheet.open(encoding="utf-8-sig", newline="") as file:
            if any(m.answerable is not None for m in marks_of(list(csv.DictReader(file)))):
                return sheet
    return None


def score(name: str, out: TextIO = sys.stdout, folder: Path = LOCAL) -> int:
    sheet = newest_marked(folder)
    if sheet is None:
        print(f"No marked sheet in {folder}: fill in the answerable column (y/n).", file=out)
        return 1
    with sheet.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    sidecar = sheet.with_suffix(".json")
    counts = json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.exists() else {}
    result = {"sheet": sheet.stem, **score_sheet(rows, counts)}
    RESULTS.mkdir(exist_ok=True)
    target = RESULTS / f"practice-{name}.json"
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2), file=out)
    return 0 if result["passed"] else 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.practice", description=__doc__)
    parser.add_argument("args", nargs="+", help="NAME, or: score NAME")
    args = parser.parse_args(argv).args
    if args[0] == "score" and len(args) == 2:
        return score(args[1])
    if len(args) == 1:
        return asyncio.run(generate(args[0]))
    parser.error("expected NAME or: score NAME")
    return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
