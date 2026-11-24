"""Practice marking eval (ADR 0029). Local only, never in CI:

    uv run --directory apps/api python -m evals.practice_marking cos330

Real AI calls on the free tier. For the topics in ``practice/<name>.yaml`` it writes practice
items on the fly through the generation service (``prepare``, ``ask``, the filter) on a
read-only dev-database session, with usage kept in memory: **nothing is stored**. It keeps
the first 10 short-answer items with at least 2 key points, a few from each topic, and gives
each three answers whose verdict is known:

- **correct:** the reference answer itself;
- **partly:** the first half of the key points (rounded up, so 2 of 3), copied from them;
- **incorrect:** the reference answer of an item on a different topic.

It marks all 30 through the same code as ``POST /practice/items/{id}/mark``
(``services.practice.marking.mark``) and writes ``evals/results/practice-marking-<name>.json``:
agreement overall and per expected verdict, the full confusion counts, and the generation
counts (items asked for, returned, kept, and dropped by reason, including the consistency
check's ``key_points_not_in_answer``, ADR 0030). Numbers only: no course text, no item and no
answer.
"""

import argparse
import asyncio
import json
import math
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, TextIO

from sqlalchemy import func, select

from app.ai.client import LLMClient
from app.ai.errors import AIUnavailable
from app.core.config import get_settings
from app.models import Topic
from app.schemas.practice import AIMarking, Verdict
from app.services.errors import AIFailed
from app.services.practice.generation import GenerationFailed, ask, keep, prepare
from app.services.practice.marking import MarkingTask, mark, marking_messages
from app.services.tutor.prompts import estimate_tokens
from app.tutor.ask import read_only_sessions
from evals.common import EVALS_DIR, find_module, load_config
from evals.tutor.__main__ import Pacer, TimedUsage

RESULTS = EVALS_DIR / "results"
ITEMS = 10
# Items asked for per topic: about 40 % come back as short answers.
PER_TOPIC = 6
VERDICTS: tuple[Verdict, ...] = ("correct", "partly", "incorrect")
# A marking turned away as busy is tried again this many times, waiting at most this long.
TRIES = 4
MAX_WAIT = 90.0


@dataclass(frozen=True)
class Item:
    topic: str
    prompt: str
    answer: str
    key_points: tuple[str, ...]


@dataclass(frozen=True)
class Case:
    item: Item
    answer: str
    expected: Verdict


def pick(by_topic: dict[str, list[Item]], count: int = ITEMS) -> list[Item]:
    """Up to ``count`` items with at least 2 key points (so "partly" exists), taken in turn
    from each topic."""
    queues = [[i for i in found if len(i.key_points) >= 2] for found in by_topic.values()]
    out: list[Item] = []
    while len(out) < count and any(queues):
        for queue in queues:
            if queue and len(out) < count:
                out.append(queue.pop(0))
    return out


def half(key_points: Sequence[str]) -> str:
    """The first half of the key points, rounded up, as an answer."""
    kept = key_points[: math.ceil(len(key_points) / 2)]
    return " ".join(p.rstrip(".") + "." for p in kept)


def cases(items: Sequence[Item]) -> list[Case]:
    """Three answers per item. The incorrect one is the reference of the next item (in turn)
    on another topic; an item with no such neighbour gets no incorrect case."""
    out: list[Case] = []
    for n, item in enumerate(items):
        out.append(Case(item, item.answer, "correct"))
        out.append(Case(item, half(item.key_points), "partly"))
        others = [o for o in [*items[n + 1 :], *items[:n]] if o.topic != item.topic]
        if others:
            out.append(Case(item, others[0].answer, "incorrect"))
    return out


def score(results: Sequence[tuple[Verdict, Verdict | None]]) -> dict[str, Any]:
    """Agreement of (expected, got) pairs; ``got`` None is a failed marking (counted as a
    disagreement)."""

    def pct(agreed: int, total: int) -> float | None:
        return round(100 * agreed / total, 1) if total else None

    agreed = sum(1 for expected, got in results if expected == got)
    per: dict[str, Any] = {}
    for verdict in VERDICTS:
        mine = [got for expected, got in results if expected == verdict]
        hits = sum(1 for got in mine if got == verdict)
        per[verdict] = {
            "cases": len(mine),
            "agreed": hits,
            "agreement_pct": pct(hits, len(mine)),
            "got": {v: sum(1 for got in mine if got == v) for v in (*VERDICTS, None)},
        }
    for found in per.values():
        found["got"]["failed"] = found["got"].pop(None)
    return {
        "cases": len(results),
        "agreed": agreed,
        "agreement_pct": pct(agreed, len(results)),
        "failed": sum(1 for _, got in results if got is None),
        "by_expected": per,
    }


async def mark_waiting(
    client: LLMClient, task: MarkingTask, *, user_id: Any, out: TextIO
) -> AIMarking:
    """``mark``, waiting out a busy minute: the marking call is interactive, so a rate limit
    or a 503 is an ``AIUnavailable`` at once. The eval waits until its ``retry_at`` (at most
    ``MAX_WAIT``) and tries again, up to ``TRIES`` times; the app never does this."""
    for attempt in range(1, TRIES + 1):
        try:
            return await mark(client, task, user_id=user_id)
        except AIUnavailable as exc:
            if attempt == TRIES or exc.retry_at is None:
                raise
            wait = min(MAX_WAIT, max(5.0, (exc.retry_at - datetime.now(UTC)).total_seconds()))
            print(f"  busy, waiting {wait:.0f} s", file=out, flush=True)
            await asyncio.sleep(wait)
    raise AssertionError("unreachable")


async def run(name: str, out: TextIO = sys.stdout) -> int:
    config = load_config(f"practice/{name}.yaml")
    settings = get_settings()
    started = time.monotonic()
    results: list[tuple[Verdict, Verdict | None]] = []
    models: dict[str, int] = {}
    generation: dict[str, Any] = {
        "requested": 0,
        "returned": 0,
        "kept": 0,
        "short_answers": 0,
        "key_points_removed": 0,
        "dropped": {},
    }
    async with read_only_sessions(settings) as sessions:
        usage = TimedUsage(sessions)
        pacer = Pacer(usage, log=out)
        client = LLMClient(settings, usage)
        try:
            async with sessions() as session:
                module_id, user_id = await find_module(session, config["module"])
                by_topic: dict[str, list[Item]] = {}
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
                        PER_TOPIC,
                        user_id=user_id,
                        max_tokens=settings.practice_context_max_tokens,
                    )
                    await pacer.before(sum(estimate_tokens(m.text) for m in prepared.messages))
                    try:
                        reply = await ask(client, prepared, user_id=user_id)
                    except (GenerationFailed, AIUnavailable) as exc:
                        print(f"Topic {len(by_topic) + 1}: generation failed ({exc})", file=out)
                        by_topic[topic_name] = []
                        continue
                    filtered = keep(reply, prepared, set(prepared.existing_keys))
                    kept = filtered.kept
                    generation["requested"] += PER_TOPIC
                    generation["returned"] += len(reply.items) + sum(reply.dropped.values())
                    generation["kept"] += len(kept)
                    generation["key_points_removed"] += reply.removed_key_points
                    generation["short_answers"] += sum(1 for i in kept if i.kind == "short_answer")
                    for reason, count in filtered.dropped.items():
                        generation["dropped"][reason] = generation["dropped"].get(reason, 0) + count
                    by_topic[topic_name] = [
                        Item(topic_name, i.prompt, i.answer, tuple(i.key_points or ()))
                        for i in kept
                        if i.kind == "short_answer"
                    ]
                    print(
                        f"Topic {len(by_topic)}: {len(by_topic[topic_name])} short answers",
                        file=out,
                        flush=True,
                    )
            items = pick(by_topic)
            todo = cases(items)
            print(f"{len(items)} items, {len(todo)} answers to mark", file=out, flush=True)
            for n, case in enumerate(todo, start=1):
                task = MarkingTask(
                    case.item.prompt, case.item.answer, case.item.key_points, case.answer
                )
                await pacer.before(sum(estimate_tokens(m.text) for m in marking_messages(task)))
                got: Verdict | None
                try:
                    found = await mark_waiting(client, task, user_id=user_id, out=out)
                    got = found.verdict
                    models[found.model] = models.get(found.model, 0) + 1
                except (AIFailed, AIUnavailable) as exc:
                    print(f"Answer {n}: marking failed ({type(exc).__name__})", file=out)
                    got = None
                results.append((case.expected, got))
                print(f"Answer {n}: expected {case.expected}, got {got}", file=out, flush=True)
        finally:
            await client.aclose()

    summary = score(results)
    summary.update(
        {
            "eval": f"practice-marking-{name}",
            "date": datetime.now(UTC).date().isoformat(),
            "items": len(items),
            "generation": generation,
            "models": models,
            "calls": len(usage.rows),
            "input_tokens": sum(r.input_tokens for r in usage.rows),
            "output_tokens": sum(r.output_tokens for r in usage.rows),
            "seconds": round(time.monotonic() - started, 1),
        }
    )
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"practice-marking-{name}.json"
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    by = summary["by_expected"]
    print(
        f"\nAgreement {summary['agreement_pct']} % of {summary['cases']} "
        f"(correct {by['correct']['agreement_pct']} %, partly {by['partly']['agreement_pct']} %, "
        f"incorrect {by['incorrect']['agreement_pct']} %), {summary['failed']} failed\n"
        f"Written: {path}",
        file=out,
    )
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.practice_marking", description=__doc__)
    parser.add_argument("name", help="the eval's name, e.g. cos330 (practice/<name>.yaml)")
    return asyncio.run(run(parser.parse_args(argv).name))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
