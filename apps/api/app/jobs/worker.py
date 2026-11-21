"""The background worker: run queued jobs one at a time.

Run it with ``uv run python -m app.jobs.worker`` (``npm run dev`` starts it).
Several workers can run at once: ``claim_next`` uses ``FOR UPDATE SKIP LOCKED``.
"""

import asyncio
import logging
from collections.abc import Callable, Mapping
from contextlib import AbstractAsyncContextManager
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.errors import AIRequestFailed, AITruncated, AIUnavailable
from app.core import clock
from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.jobs import queue
from app.jobs.context import Handler, JobContext, JobError
from app.jobs.kinds import (
    EXTRACT_TEXT,
    EXTRACT_TOPICS,
    INDEX_MATERIAL,
    LINK_TOPICS,
    MERGE_TOPICS,
    PUSH_REMINDER,
    REPLAN,
)
from app.jobs.tasks import (
    extract_text,
    extract_topics,
    index_material,
    link_topics,
    merge_topics,
    push_reminder,
    replan,
)
from app.services.planning.replan import queue_nightly_replans
from app.services.push.reminders import prune_reminders_sent, queue_reminders
from app.services.search.embedding import get_embedder
from app.storage.base import Storage
from app.storage.local import get_storage

log = logging.getLogger("studysensei.worker")

HANDLERS: Mapping[str, Handler] = {
    EXTRACT_TEXT: Handler(run=extract_text.run, on_failure=extract_text.on_failure),
    INDEX_MATERIAL: Handler(run=index_material.run, on_failure=index_material.on_failure),
    EXTRACT_TOPICS: Handler(run=extract_topics.run, on_failure=extract_topics.on_failure),
    MERGE_TOPICS: Handler(run=merge_topics.run),
    LINK_TOPICS: Handler(run=link_topics.run),
    REPLAN: Handler(run=replan.run),
    PUSH_REMINDER: Handler(run=push_reminder.run),
}
# How often the main loop looks for users due a nightly re-plan (decision 0021) and for
# blocks due a push reminder (decision 0024), and prunes old reminder records.
NIGHTLY_CHECK_SECONDS = 60.0

UNEXPECTED = "Something went wrong while processing this file. It will be retried."
GAVE_UP = "Something went wrong while processing this file."

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


def _now() -> datetime:
    return clock.now()


async def run_once(
    sessions: SessionFactory,
    storage: Storage,
    *,
    now: Callable[[], datetime] = _now,
    handlers: Mapping[str, Handler] = HANDLERS,
) -> bool:
    """Claim and run one due job. Returns False if there was nothing to do."""
    async with sessions() as session:
        job = await queue.claim_next(session, now())
    if job is None:
        return False

    handler = handlers.get(job.kind)
    async with sessions() as session:
        ctx = JobContext(session, job, storage, now)
        try:
            if handler is None:
                raise JobError(f"Unknown job kind {job.kind!r}")
            try:
                await handler.run(ctx)
            except AIUnavailable as exc:
                if exc.retry_at is None:
                    # No provider is set up: waiting won't help, so fail with the reason.
                    raise JobError(str(exc), retry=False) from exc
                raise
            except (AIRequestFailed, AITruncated) as exc:
                # Refused or cut off: the same request would fail the same way.
                raise JobError(str(exc), retry=False) from exc
        except AIUnavailable as exc:
            # Rate limits or quotas: not the job's fault, so run it again when they reset.
            await session.rollback()
            assert exc.retry_at is not None
            await queue.reschedule(session, job, exc.retry_at, f"AIUnavailable: {exc}")
            log.info("Job %s (%s) waits for AI until %s", job.id, job.kind, exc.retry_at)
        except Exception as exc:
            await session.rollback()
            expected = isinstance(exc, JobError)
            if not expected:
                log.exception("Job %s (%s) failed on attempt %s", job.id, job.kind, job.attempts)
            give_up = isinstance(exc, JobError) and not exc.retry
            retrying = await queue.fail(
                session, job, f"{type(exc).__name__}: {exc}", now(), give_up=give_up
            )
            message = str(exc) if expected else (UNEXPECTED if retrying else GAVE_UP)
            if handler is not None and handler.on_failure is not None:
                await handler.on_failure(ctx, message, retrying=retrying)
        else:
            await queue.complete(session, job, now())
            log.info("Job %s (%s) done", job.id, job.kind)
    return True


async def main() -> None:
    settings = get_settings()
    storage = get_storage()
    sessions = get_sessionmaker()
    idle = settings.worker_poll_seconds
    if settings.preload_embedder:
        # Indexing and topic linking need it; loading it now keeps the first job quick.
        await asyncio.to_thread(get_embedder)
    log.info("Worker started; polling every %.1fs", idle)
    failures = 0
    last_nightly_check = float("-inf")
    loop = asyncio.get_running_loop()
    try:
        while True:
            try:
                if loop.time() - last_nightly_check >= NIGHTLY_CHECK_SECONDS:
                    last_nightly_check = loop.time()
                    async with sessions() as session:
                        queued = await queue_nightly_replans(session, _now())
                    if queued:
                        log.info("Queued %s nightly re-plan(s)", queued)
                    async with sessions() as session:
                        reminders = await queue_reminders(session, _now())
                    if reminders:
                        log.info("Queued %s push reminder(s)", reminders)
                    async with sessions() as session:
                        pruned = await prune_reminders_sent(session, _now())
                    if pruned:
                        log.info("Pruned %s reminder record(s) over 30 days old", pruned)
                ran = await run_once(sessions, storage)
                failures = 0
            except Exception:
                # The database is down or restarting: wait longer each time, up to a minute.
                failures += 1
                log.exception("Worker loop error (%s in a row)", failures)
                await asyncio.sleep(min(60.0, idle * 2**failures))
                continue
            if not ran:
                await asyncio.sleep(idle)
    finally:
        await get_engine().dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Worker stopped")
