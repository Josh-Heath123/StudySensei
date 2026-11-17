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

# Outcomes that used up a request of the provider's quota (a 429 was refused, so it didn't).
# A timeout counts: the provider may well have answered after we stopped waiting.
COUNTED_OUTCOMES = ("ok", "error", "invalid_json", "timeout", "truncated")


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


async def job_calls(
    session: AsyncSession, job_id: uuid.UUID, *, user_id: uuid.UUID
) -> tuple[int, int]:
    """(provider calls, repair-worthy invalid replies) a job has made so far, across retries."""
    rows = await session.execute(
        select(AIUsage.outcome, func.count())
        .where(AIUsage.user_id == user_id, AIUsage.job_id == job_id)
        .group_by(AIUsage.outcome)
    )
    counts: dict[str, int] = {outcome: count for outcome, count in rows}
    return sum(counts.values()), counts.get("invalid_json", 0)


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
