"""The Postgres job queue (decision 0004).

- ``enqueue`` adds a job in the caller's transaction, so a job exists exactly
  when the change that needs it is committed.
- ``enqueue_replan`` does the same for a re-plan, but coalesces: at most one is queued per
  user (a partial unique index), and the first trigger is kept (decision 0021).
- ``claim_next`` takes the next due job with ``FOR UPDATE SKIP LOCKED``, so
  workers never take the same job, and puts back jobs whose worker died.
- ``fail`` schedules a retry with exponential backoff, or gives up.
"""

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.jobs.kinds import REPLAN
from app.models import Job

BACKOFF_BASE = timedelta(seconds=30)
BACKOFF_FACTOR = 4
BACKOFF_CAP = timedelta(minutes=30)
# A running job locked longer than this belonged to a worker that died.
STALE_LOCK = timedelta(minutes=10)
# Error text is kept short: it's for people, not a log.
MAX_ERROR_CHARS = 500


def backoff(attempt: int) -> timedelta:
    """Delay before retrying after failed attempt number ``attempt`` (1-based)."""
    factor: int = BACKOFF_FACTOR ** max(0, attempt - 1)
    return min(BACKOFF_BASE * factor, BACKOFF_CAP)


def enqueue(
    session: AsyncSession,
    kind: str,
    payload: dict[str, Any],
    *,
    user_id: uuid.UUID,
    max_attempts: int = 3,
) -> Job:
    """Add a job to the session (committed with the caller's transaction)."""
    job = Job(
        user_id=user_id,
        kind=kind,
        payload=payload,
        max_attempts=max_attempts,
        run_after=clock.now(),
    )
    session.add(job)
    return job


async def enqueue_replan(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    trigger: str,
    detail: dict[str, Any] | None = None,
) -> None:
    """Queue a re-plan for the user in the caller's transaction, unless one is already queued
    (then this one is folded into it, and the queued job keeps its first trigger). A re-plan
    that's running doesn't count: a change during it queues the next one."""
    await session.execute(
        insert(Job)
        .values(
            id=uuid.uuid4(),
            user_id=user_id,
            kind=REPLAN,
            payload={"trigger": trigger, "detail": detail or {}},
            max_attempts=3,
            run_after=clock.now(),
        )
        .on_conflict_do_nothing(
            index_elements=["user_id"],
            index_where=text("kind = 'replan' AND status = 'queued'"),
        )
    )


async def claim_next(session: AsyncSession, now: datetime) -> Job | None:
    """Lock and mark running the next due job, or return None. Commits."""
    due = or_(
        (Job.status == "queued") & (Job.run_after <= now),
        (Job.status == "running") & (Job.locked_at < now - STALE_LOCK),
    )
    job = await session.scalar(
        select(Job)
        .where(due)
        .order_by(Job.run_after, Job.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        await session.rollback()
        return None
    job.status = "running"
    job.locked_at = now
    job.attempts += 1
    await session.commit()
    # Detached: the handler's rollbacks can't expire it (complete/fail update by id).
    session.expunge(job)
    return job


async def complete(session: AsyncSession, job: Job, now: datetime) -> None:
    await session.execute(
        update(Job)
        .where(Job.id == job.id)
        .values(status="succeeded", locked_at=None, finished_at=now, last_error=None)
    )
    await session.commit()


async def reschedule(session: AsyncSession, job: Job, run_after: datetime, reason: str) -> None:
    """Put a job back to run at ``run_after`` without using up an attempt. Commits.

    For waits that aren't the job's fault, such as AI quotas running out.
    """
    await session.execute(
        update(Job)
        .where(Job.id == job.id)
        .values(
            status="queued",
            run_after=run_after,
            locked_at=None,
            attempts=Job.attempts - 1,
            last_error=reason[:MAX_ERROR_CHARS],
        )
    )
    await session.commit()


async def fail(
    session: AsyncSession, job: Job, error: str, now: datetime, *, give_up: bool = False
) -> bool:
    """Record a failed attempt. Returns True if the job will be retried. Commits."""
    retry = not give_up and job.attempts < job.max_attempts
    values: dict[str, Any] = {"locked_at": None, "last_error": error[:MAX_ERROR_CHARS]}
    if retry:
        values |= {"status": "queued", "run_after": now + backoff(job.attempts)}
    else:
        values |= {"status": "failed", "finished_at": now}
    await session.execute(update(Job).where(Job.id == job.id).values(**values))
    await session.commit()
    return retry
