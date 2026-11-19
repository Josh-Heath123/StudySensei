"""Ask the tutor from the command line, on real data, with the service the API uses.

    uv run python -m app.tutor.ask --module COS330 "What is a salt?" [--topic NAME]
        [--mode answer|explain_differently|example|quiz] [--dry-run]

It prints the sources, streams the answer, then the model, the time to first token, the
cited sources and the AI calls made. It asks as the local user (``LOCAL_USER_EMAIL``).

- Without ``--dry-run``: a new conversation, stored like one from the API (needs
  migration 0017), and the AI calls are logged in ``ai_usage``.
- With ``--dry-run``: nothing is written. The database session is read-only in Postgres
  itself, and the AI calls are kept in memory (today's earlier calls still count toward
  the daily budgets). The calls are real: they use the free tier.
"""

import argparse
import asyncio
import sys
import time
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import datetime
from typing import TextIO

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.ai.client import LLMClient, TextDelta
from app.ai.usage import COUNTED_OUTCOMES, DbUsageStore, UsageRecord, UsageStore
from app.core.config import Settings, get_settings
from app.models import Module, Topic, User
from app.schemas.tutor import (
    ConversationCreate,
    DeltaEvent,
    DoneEvent,
    ErrorEvent,
    MessageCreate,
    SourcesEvent,
)
from app.services.search.embedding import get_embedder
from app.services.tutor.conversations import (
    FOLLOW_UP_MODES,
    HISTORY_STATUSES,
    create_conversation,
    prepare_message,
    run_turn,
)
from app.services.tutor.prompts import TUTOR_MODES, Exchange, TutorMode
from app.services.tutor.retrieval import PreviousSource, Source
from app.services.tutor.turn import Answer, answer, build_turn

Sessions = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class MemoryUsage:
    """Usage for a dry run: today's rows are read from the database, new ones kept here."""

    def __init__(self, sessions: Sessions) -> None:
        self._db = DbUsageStore(sessions)
        self.rows: list[UsageRecord] = []

    async def count_since(
        self, *, user_id: uuid.UUID, provider: str, model: str, since: datetime
    ) -> int:
        earlier = await self._db.count_since(
            user_id=user_id, provider=provider, model=model, since=since
        )
        mine = sum(
            1
            for row in self.rows
            if (row.provider, row.model) == (provider, model) and row.outcome in COUNTED_OUTCOMES
        )
        return earlier + mine

    async def record(self, row: UsageRecord) -> None:
        self.rows.append(row)


class LoggingUsage:
    """Usage written to the database as usual, and remembered for the summary."""

    def __init__(self, inner: UsageStore) -> None:
        self._inner = inner
        self.rows: list[UsageRecord] = []

    async def count_since(
        self, *, user_id: uuid.UUID, provider: str, model: str, since: datetime
    ) -> int:
        return await self._inner.count_since(
            user_id=user_id, provider=provider, model=model, since=since
        )

    async def record(self, row: UsageRecord) -> None:
        self.rows.append(row)
        await self._inner.record(row)


async def find_module_and_topic(
    session: AsyncSession, settings: Settings, code: str, topic_name: str | None
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID | None]:
    """(user id, module id, topic id) for the local user's module with this code."""
    user_id = await session.scalar(select(User.id).where(User.email == settings.local_user_email))
    if user_id is None:
        raise SystemExit(f"No local user {settings.local_user_email}. Run `npm run db:seed`.")
    module_id = await session.scalar(
        select(Module.id).where(Module.user_id == user_id, Module.code == code.upper())
    )
    if module_id is None:
        raise SystemExit(f"No module {code!r} for the local user.")
    if topic_name is None:
        return user_id, module_id, None
    topics = list(
        await session.scalars(
            select(Topic.id).where(
                Topic.user_id == user_id,
                Topic.module_id == module_id,
                func.lower(Topic.name) == topic_name.strip().lower(),
            )
        )
    )
    if len(topics) != 1:
        raise SystemExit(f"Expected one topic named {topic_name!r} in {code}, found {len(topics)}.")
    return user_id, module_id, topics[0]


def source_line(source: Source) -> str:
    title = f" · {source.page_title}" if source.page_title else ""
    return f"  {source.label} {source.material_title} p{source.page_number}{title}"


def print_sources(event: SourcesEvent, out: TextIO) -> None:
    print(f"Sources ({len(event.sources)}):", file=out)
    for s in event.sources:
        title = f" · {s.page_title}" if s.page_title else ""
        print(f"  {s.label} {s.material_title} p{s.page_number}{title}", file=out)
    print("\nAnswer:", file=out, flush=True)


def print_calls(rows: list[UsageRecord], out: TextIO) -> None:
    calls = ", ".join(f"{r.provider}/{r.model} {r.outcome} ({r.latency_ms} ms)" for r in rows)
    counted = sum(1 for r in rows if r.outcome in COUNTED_OUTCOMES)
    print(f"AI calls: {len(rows)} ({counted} counted against the free tier): {calls}", file=out)


@asynccontextmanager
async def read_only_sessions(settings: Settings) -> AsyncIterator[Sessions]:
    """Sessions on the database in settings that Postgres itself won't let write."""
    engine = create_async_engine(
        settings.database_url,
        connect_args={"server_settings": {"default_transaction_read_only": "on"}},
    )
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def dry_run(
    args: argparse.Namespace,
    settings: Settings,
    out: TextIO,
    sessions: Sessions,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[Answer | None, list[UsageRecord]]:
    """The turn without writing anything: ``sessions`` should be read-only, and usage is
    kept in memory. (Tests pass their own sessions and a fake transport.)"""
    usage = MemoryUsage(sessions)
    client = LLMClient(settings, usage, transport=transport)
    result: Answer | None = None
    try:
        async with sessions() as session:
            user_id, module_id, topic_id = await find_module_and_topic(
                session, settings, args.module, args.topic
            )
            # The API loads the embedding model once per process (its first search), so
            # it's loaded before the clock starts: the times below are a warm API's.
            loading = time.monotonic()
            embedder = await asyncio.to_thread(get_embedder)
            load_ms = int((time.monotonic() - loading) * 1000)
            history: list[Exchange] = []
            reuse: list[PreviousSource] = []
            previous_question: str | None = None
            if args.after:
                # The earlier question, answered for real, then this one as its follow-up:
                # the rules of conversations.prepare_message, without storing anything.
                before = await build_turn(
                    session,
                    module_id,
                    args.after,
                    "answer",
                    user_id=user_id,
                    topic_id=topic_id,
                    history=[],
                    embedder=embedder,
                    settings=settings,
                )
                earlier: Answer | None = None
                async for event in answer(before, client=client, user_id=user_id):
                    if isinstance(event, Answer):
                        earlier = event
                print(f"Earlier question: {args.after}", file=out)
                if earlier is not None:
                    print_result(earlier, before.sources, out)
                    print(file=out)
                    if earlier.status in HISTORY_STATUSES and earlier.text.strip():
                        history = [Exchange(args.after, earlier.text)]
                if args.mode in FOLLOW_UP_MODES:
                    reuse = [
                        PreviousSource(s.label, s.chunk_id, s.material_id, s.page_number)
                        for s in before.sources
                    ]
                else:
                    previous_question = args.after
            started = time.monotonic()
            turn = await build_turn(
                session,
                module_id,
                args.question,
                args.mode,
                user_id=user_id,
                topic_id=topic_id,
                history=history,
                embedder=embedder,
                settings=settings,
                started=started,
                previous_question=previous_question,
                reuse=reuse,
            )
            print(
                f"Context: {turn.context_tokens} estimated tokens of sources "
                f"(budget {settings.tutor_context_max_tokens}); retrieval "
                f"{int((time.monotonic() - started) * 1000)} ms (embedding model load "
                f"{load_ms} ms, not counted)\n",
                file=out,
            )
            async for event in answer(turn, client=client, user_id=user_id):
                if isinstance(event, SourcesEvent):
                    print_sources(event, out)
                elif isinstance(event, TextDelta):
                    out.write(event.text)
                    out.flush()
                else:
                    result = event
            if result is not None:
                print_result(result, turn.sources, out)
    finally:
        await client.aclose()
    return result, usage.rows


def print_result(result: Answer, sources: list[Source], out: TextIO) -> None:
    by_label = {s.label: s for s in sources}
    print("\n", file=out)
    print(
        f"Status: {result.status} · model {result.model or '-'} · first token "
        f"{result.first_token_ms if result.first_token_ms is not None else '-'} ms · "
        f"total {result.total_ms} ms",
        file=out,
    )
    if result.error:
        print(f"Error: {result.error}", file=out)
    print("Cited:", "none" if not result.cited else "", file=out)
    for label in result.cited:
        print(source_line(by_label[label]), file=out)
    if result.unknown_citations:
        print(f"Unknown labels: {', '.join(result.unknown_citations)}", file=out)


async def stored_run(
    args: argparse.Namespace, settings: Settings, out: TextIO
) -> list[UsageRecord]:
    """A stored conversation, exactly as the API runs it."""
    from app.core.db import get_engine, get_sessionmaker

    usage = LoggingUsage(DbUsageStore(get_sessionmaker()))
    client = LLMClient(settings, usage)
    try:
        async with get_sessionmaker()() as session:
            user_id, module_id, topic_id = await find_module_and_topic(
                session, settings, args.module, args.topic
            )
            conversation = await create_conversation(
                session, module_id, ConversationCreate(topic_id=topic_id), user_id=user_id
            )
            embedder = await asyncio.to_thread(get_embedder)
            prepared = await prepare_message(
                session,
                conversation.id,
                MessageCreate(question=args.question, mode=args.mode),
                user_id=user_id,
                embedder=embedder,
                settings=settings,
            )
            async for event in run_turn(session, prepared, client=client):
                if isinstance(event, SourcesEvent):
                    print_sources(event, out)
                elif isinstance(event, DeltaEvent):
                    out.write(event.text)
                    out.flush()
                elif isinstance(event, DoneEvent):
                    print(
                        f"\n\nStatus: {event.status} · model {event.model} · first token "
                        f"{event.first_token_ms} ms · total {event.total_ms} ms\n"
                        f"Cited: {', '.join(event.cited) or 'none'}"
                        + (
                            f" (unknown: {', '.join(event.unknown_citations)})"
                            if event.unknown_citations
                            else ""
                        )
                        + f"\nStored as conversation {conversation.id}",
                        file=out,
                    )
                elif isinstance(event, ErrorEvent):
                    print(f"\n\nError: {event.message}", file=out)
    finally:
        await client.aclose()
        await get_engine().dispose()
    return usage.rows


def parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m app.tutor.ask", description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--module", required=True, help="module code, e.g. COS330")
    parser.add_argument("--topic", help="the session topic retrieval boosts (its exact name)")
    parser.add_argument("--mode", choices=TUTOR_MODES, default="answer")
    parser.add_argument("--dry-run", action="store_true", help="write nothing to the database")
    parser.add_argument(
        "--after",
        metavar="QUESTION",
        help="with --dry-run: ask this first, then the question as its follow-up (two calls)",
    )
    return parser.parse_args(argv)


async def main(argv: list[str], out: TextIO = sys.stdout) -> int:
    args = parse(argv)
    mode: TutorMode = args.mode
    args.mode = mode
    settings = get_settings()
    if args.after and not args.dry_run:
        raise SystemExit("--after works with --dry-run only.")
    if args.dry_run:
        async with read_only_sessions(settings) as sessions:
            result, rows = await dry_run(args, settings, out, sessions)
        print_calls(rows, out)
        return 0 if result is not None and result.status != "failed" else 1
    rows = await stored_run(args, settings, out)
    print_calls(rows, out)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(asyncio.run(main(sys.argv[1:])))
