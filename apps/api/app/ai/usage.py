"""Reading and writing ``ai_usage`` rows (never prompt or reply text)."""

import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AIUsage

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]

# Outcomes that used up a request of the provider's quota. A timeout counts: the provider
# may well have answered after we stopped waiting. A refusal ran (and was filtered). A
# stream the student stopped part-way ran too.
COUNTED_OUTCOMES = ("ok", "error", "invalid_json", "timeout", "truncated", "refused", "stopped")
# Requests the provider turned away before running them: 429, 503 "high demand", and 413
# "request too large" (ADR 0009).
TURNED_AWAY_OUTCOMES = ("rate_limited", "overloaded", "too_large")


@dataclass(frozen=True)
class UsageRecord:
    user_id: uuid.UUID
    provider: str
    model: str
    role: str
    purpose: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    outcome: str
    job_id: uuid.UUID | None = None
    detail: str | None = None


async def count_requests(
    session: AsyncSession, *, user_id: uuid.UUID, provider: str, model: str, since: datetime
) -> int:
    """The user's requests to one model since ``since`` that count against its quota."""
    count = await session.scalar(
        select(func.count())
        .select_from(AIUsage)
        .where(
            AIUsage.user_id == user_id,
            AIUsage.provider == provider,
            AIUsage.model == model,
            AIUsage.created_at >= since,
            AIUsage.outcome.in_(COUNTED_OUTCOMES),
        )
    )
    return int(count or 0)


@dataclass(frozen=True)
class JobCalls:
    """What a job has spent so far, across its retries and reschedules."""

    # Calls the provider ran (everything but the turned-away ones).
    ran: int
    # Requests turned away before running (429, 503).
    turned_away: int
    # Replies that didn't validate (each one needed the repair).
    invalid: int


async def job_calls(session: AsyncSession, job_id: uuid.UUID, *, user_id: uuid.UUID) -> JobCalls:
    """A job's provider calls so far, across retries (``JobCalls``)."""
    rows = await session.execute(
        select(AIUsage.outcome, func.count())
        .where(AIUsage.user_id == user_id, AIUsage.job_id == job_id)
        .group_by(AIUsage.outcome)
    )
    counts: dict[str, int] = {outcome: count for outcome, count in rows}
    turned_away = sum(counts.get(o, 0) for o in TURNED_AWAY_OUTCOMES)
    return JobCalls(
        ran=sum(counts.values()) - turned_away,
        turned_away=turned_away,
        invalid=counts.get("invalid_json", 0),
    )


class UsageStore(Protocol):
    async def count_since(
        self, *, user_id: uuid.UUID, provider: str, model: str, since: datetime
    ) -> int: ...

    async def record(self, row: UsageRecord) -> None: ...


class DbUsageStore:
    """Writes each row in its own session and commits at once.

    A job that rolls back its own work still leaves its AI calls on record.
    """

    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    async def count_since(
        self, *, user_id: uuid.UUID, provider: str, model: str, since: datetime
    ) -> int:
        async with self._sessions() as session:
            return await count_requests(
                session, user_id=user_id, provider=provider, model=model, since=since
            )

    async def record(self, row: UsageRecord) -> None:
        async with self._sessions() as session:
            session.add(
                AIUsage(
                    user_id=row.user_id,
                    provider=row.provider,
                    model=row.model,
                    role=row.role,
                    purpose=row.purpose,
                    input_tokens=row.input_tokens,
                    output_tokens=row.output_tokens,
                    latency_ms=row.latency_ms,
                    outcome=row.outcome,
                    job_id=row.job_id,
                    detail=row.detail[:300] if row.detail else None,
                )
            )
            await session.commit()
