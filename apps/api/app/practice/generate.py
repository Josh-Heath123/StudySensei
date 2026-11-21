"""Write practice items for a topic from the command line, with the service the job uses.

    uv run python -m app.practice.generate --module COS330 --topic "NAME" [--count 8]
        [--dry-run]

It works as the local user (``LOCAL_USER_EMAIL``) on the dev database.

- With ``--dry-run``: nothing is written. The database session is read-only in Postgres
  itself and the AI calls are kept in memory (today's earlier calls still count toward the
  daily budgets). It prints each kept item with its cited material and page and the first
  200 characters of each source, then the counts, tokens and time, **to the terminal only**:
  it never writes a file. The calls are real: they use the free tier.
- Without it (dev only): a generation is stored exactly as the job stores one, and the AI
  calls are logged in ``ai_usage``.
"""

import argparse
import asyncio
import sys
import time
import uuid
from collections.abc import Sequence
from typing import TextIO

import httpx
from sqlalchemy import select

from app.ai.client import LLMClient
from app.ai.errors import AIUnavailable
from app.ai.usage import DbUsageStore, UsageRecord
from app.core import clock
from app.core.config import Settings, get_settings
from app.models import PracticeGeneration, Topic
from app.schemas.practice import GENERATE_DEFAULT, GENERATE_MAX, GENERATE_MIN, GeneratedItem
from app.services.practice.filter import Filtered
from app.services.practice.generation import (
    GenerationFailed,
    Prepared,
    ask,
    keep,
    prepare,
    request_generation,
    store,
)
from app.tutor.ask import (
    LoggingUsage,
    MemoryUsage,
    Sessions,
    find_module_and_topic,
    print_calls,
    read_only_sessions,
)

PREVIEW = 200


def print_sources(prepared: Prepared, out: TextIO) -> None:
    found = prepared.sources
    print(
        f"Sources: {len(found.sources)} passages, {found.context_tokens} estimated tokens "
        f"({found.dropped} left out by the budget)",
        file=out,
    )


def print_items(kept: Sequence[GeneratedItem], prepared: Prepared, out: TextIO) -> None:
    by_label = {s.label: s for s in prepared.sources.sources}
    for number, item in enumerate(kept, start=1):
        print(f"\n{number}. [{item.kind}] {item.prompt}", file=out)
        print(f"   Answer: {item.answer}", file=out)
        for point in item.key_points or []:
            print(f"   - {point}", file=out)
        for label in dict.fromkeys(item.sources):
            source = by_label[label]
            text = " ".join(source.text.split())
            print(f"   {label}: {source.material_title} p{source.page_number}", file=out)
            print(f"       {text[:PREVIEW]}{'…' if len(text) > PREVIEW else ''}", file=out)


def print_counts(
    requested: int,
    returned: int,
    filtered: Filtered,
    rows: Sequence[UsageRecord],
    seconds: float,
    model: str | None,
    out: TextIO,
) -> None:
    dropped = ", ".join(f"{k} {v}" for k, v in sorted(filtered.dropped.items())) or "none"
    tokens_in = sum(r.input_tokens for r in rows)
    tokens_out = sum(r.output_tokens for r in rows)
    print(
        f"\nRequested {requested} · returned {returned} · kept {len(filtered.kept)} · "
        f"dropped: {dropped}\nTokens: {tokens_in} in, {tokens_out} out · "
        f"{seconds:.1f} s · model {model or '-'}",
        file=out,
    )


async def _topic(session_topic: tuple[uuid.UUID, uuid.UUID, uuid.UUID | None]) -> uuid.UUID:
    _, _, topic_id = session_topic
    if topic_id is None:
        raise SystemExit("--topic is required.")
    return topic_id


async def dry_run(
    args: argparse.Namespace,
    settings: Settings,
    out: TextIO,
    sessions: Sessions,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> int:
    """Prepare, ask and filter, storing nothing. (Tests pass their own sessions and a fake
    transport.)"""
    usage = MemoryUsage(sessions)
    client = LLMClient(settings, usage, transport=transport)
    started = time.monotonic()
    try:
        async with sessions() as session:
            found = await find_module_and_topic(session, settings, args.module, args.topic)
            user_id, topic_id = found[0], await _topic(found)
            topic = await session.scalar(
                select(Topic).where(Topic.id == topic_id, Topic.user_id == user_id)
            )
            assert topic is not None
            prepared = await prepare(
                session,
                topic,
                args.count,
                user_id=user_id,
                max_tokens=settings.practice_context_max_tokens,
            )
            print_sources(prepared, out)
            try:
                reply = await ask(client, prepared, user_id=user_id)
            except (GenerationFailed, AIUnavailable) as exc:
                print(f"Failed: {exc}", file=out)
                print_calls(usage.rows, out)
                return 1
            filtered = keep(reply.items, prepared, set(prepared.existing_keys))
            print_items(filtered.kept, prepared, out)
            print_counts(
                args.count,
                len(reply.items),
                filtered,
                usage.rows,
                time.monotonic() - started,
                f"{reply.route.provider.name}/{reply.route.model}",
                out,
            )
    finally:
        await client.aclose()
    print_calls(usage.rows, out)
    return 0


async def stored_run(args: argparse.Namespace, settings: Settings, out: TextIO) -> int:
    """A stored generation, as the job writes one (dev only)."""
    from app.core.db import get_engine, get_sessionmaker

    usage = LoggingUsage(DbUsageStore(get_sessionmaker()))
    client = LLMClient(settings, usage)
    started = time.monotonic()
    try:
        async with get_sessionmaker()() as session:
            found = await find_module_and_topic(session, settings, args.module, args.topic)
            user_id, topic_id = found[0], await _topic(found)
            generation = await request_generation(session, topic_id, args.count, user_id=user_id)
            generation_id = generation.id
            topic = await session.scalar(select(Topic).where(Topic.id == topic_id))
            assert topic is not None
            prepared = await prepare(
                session,
                topic,
                args.count,
                user_id=user_id,
                max_tokens=settings.practice_context_max_tokens,
            )
            await session.commit()
            print_sources(prepared, out)
            reply = await ask(client, prepared, user_id=user_id)
            done = await store(
                session, generation_id, prepared, reply, user_id=user_id, now=clock.now()
            )
            stored = await session.get(PracticeGeneration, generation_id)
            print(
                f"Stored generation {generation_id}: "
                f"{stored.produced if stored else 0} items; dropped "
                f"{stored.dropped if stored else {}}; {time.monotonic() - started:.1f} s"
                + ("" if done else " (it was already finished)"),
                file=out,
            )
    finally:
        await client.aclose()
        await get_engine().dispose()
    print_calls(usage.rows, out)
    return 0


def count(value: str) -> int:
    number = int(value)
    if not GENERATE_MIN <= number <= GENERATE_MAX:
        raise argparse.ArgumentTypeError(f"between {GENERATE_MIN} and {GENERATE_MAX}")
    return number


def parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m app.practice.generate", description=__doc__)
    parser.add_argument("--module", required=True, help="module code, e.g. COS330")
    parser.add_argument("--topic", required=True, help="the topic's exact name")
    parser.add_argument("--count", type=count, default=GENERATE_DEFAULT)
    parser.add_argument("--dry-run", action="store_true", help="write nothing to the database")
    return parser.parse_args(argv)


async def main(argv: list[str], out: TextIO = sys.stdout) -> int:
    args = parse(argv)
    settings = get_settings()
    if args.dry_run:
        async with read_only_sessions(settings) as sessions:
            return await dry_run(args, settings, out, sessions)
    return await stored_run(args, settings, out)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(asyncio.run(main(sys.argv[1:])))
