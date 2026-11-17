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
COUNTED_OUTCOMES = ("ok", "error", "invalid_json", "timeout")


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
                )
            )
            await session.commit()
