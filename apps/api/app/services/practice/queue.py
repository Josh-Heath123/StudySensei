"""The review queue (ADR 0026). Every query is scoped by ``user_id``.

Order: active items that are due (their state's ``due`` is now or earlier), oldest due first;
then new active items (no state yet), oldest first, up to today's allowance:
``practice_new_per_day`` less the new items first reviewed today. "Today" is the local date in
``users.timezone``, from its local midnight (so a DST change doesn't move it). A first review
is one whose ``state_before`` is null with a ``state_after``: reviews from before scheduling
(task 1) don't count.

The counts: due now, new items that can still be reviewed today (the allowance left, capped
by the new items there are), the allowance left itself, new in all, and the next due time
after now.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PracticeItem, PracticeItemState, Review, User
from app.schemas.practice import ItemOut, PracticeSettingsOut, PracticeSettingsUpdate, QueueCounts
from app.services.errors import NotFound
from app.services.practice.items import items_out

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


@dataclass(frozen=True)
class Scope:
    module_id: uuid.UUID | None = None
    topic_id: uuid.UUID | None = None


EVERYTHING = Scope()


def today_bounds(now: datetime, timezone: str) -> tuple[datetime, datetime]:
    """The local day containing ``now``: its midnight and the next, as aware times."""
    tz = ZoneInfo(timezone)
    day = now.astimezone(tz).date()
    start = datetime.combine(day, time(0), tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), time(0), tzinfo=tz)
    return start, end


def _scoped(query: Select[Any], user_id: uuid.UUID, scope: Scope) -> Select[Any]:
    query = query.where(PracticeItem.user_id == user_id, PracticeItem.status == "active")
    if scope.module_id is not None:
        query = query.where(PracticeItem.module_id == scope.module_id)
    if scope.topic_id is not None:
        query = query.where(PracticeItem.topic_id == scope.topic_id)
    return query


def _with_state(query: Select[Any]) -> Select[Any]:
    return query.join(
        PracticeItemState,
        (PracticeItemState.item_id == PracticeItem.id)
        & (PracticeItemState.user_id == PracticeItem.user_id),
    )


def _without_state(query: Select[Any]) -> Select[Any]:
    return query.outerjoin(
        PracticeItemState,
        (PracticeItemState.item_id == PracticeItem.id)
        & (PracticeItemState.user_id == PracticeItem.user_id),
    ).where(PracticeItemState.item_id.is_(None))


async def _user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFound("User")
    return user


async def new_reviewed_today(
    session: AsyncSession, *, user_id: uuid.UUID, now: datetime, timezone: str
) -> int:
    start, end = today_bounds(now, timezone)
    found = await session.scalar(
        select(func.count(func.distinct(Review.item_id))).where(
            Review.user_id == user_id,
            Review.state_before.is_(None),
            Review.state_after.is_not(None),
            Review.reviewed_at >= start,
            Review.reviewed_at < end,
        )
    )
    return int(found or 0)


async def queue_counts(
    session: AsyncSession, *, user_id: uuid.UUID, now: datetime, scope: Scope = EVERYTHING
) -> QueueCounts:
    user = await _user(session, user_id)
    due_now = await session.scalar(
        _scoped(_with_state(select(func.count()).select_from(PracticeItem)), user_id, scope).where(
            PracticeItemState.due <= now
        )
    )
    new_total = await session.scalar(
        _scoped(_without_state(select(func.count()).select_from(PracticeItem)), user_id, scope)
    )
    next_due = await session.scalar(
        _scoped(
            _with_state(select(func.min(PracticeItemState.due)).select_from(PracticeItem)),
            user_id,
            scope,
        ).where(PracticeItemState.due > now)
    )
    used = await new_reviewed_today(session, user_id=user_id, now=now, timezone=user.timezone)
    allowance = max(0, user.practice_new_per_day - used)
    return QueueCounts(
        due_now=int(due_now or 0),
        new_today_left=min(allowance, int(new_total or 0)),
        new_allowance_left=allowance,
        new_total=int(new_total or 0),
        next_due_at=next_due,
    )


async def review_queue(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    now: datetime,
    scope: Scope = EVERYTHING,
    limit: int = DEFAULT_LIMIT,
) -> tuple[list[ItemOut], QueueCounts]:
    """The next items to review, in order, and the queue's counts."""
    counts = await queue_counts(session, user_id=user_id, now=now, scope=scope)
    due = list(
        await session.scalars(
            _scoped(_with_state(select(PracticeItem)), user_id, scope)
            .where(PracticeItemState.due <= now)
            .order_by(PracticeItemState.due, PracticeItem.id)
            .limit(limit)
        )
    )
    room = min(limit - len(due), counts.new_today_left)
    new = (
        list(
            await session.scalars(
                _scoped(_without_state(select(PracticeItem)), user_id, scope)
                .order_by(PracticeItem.created_at, PracticeItem.id)
                .limit(room)
            )
        )
        if room > 0
        else []
    )
    return await items_out(session, [*due, *new], user_id=user_id, now=now), counts


async def get_settings(session: AsyncSession, *, user_id: uuid.UUID) -> PracticeSettingsOut:
    user = await _user(session, user_id)
    return PracticeSettingsOut(
        new_per_day=user.practice_new_per_day, desired_retention=user.practice_desired_retention
    )


async def update_settings(
    session: AsyncSession, data: PracticeSettingsUpdate, *, user_id: uuid.UUID
) -> PracticeSettingsOut:
    """A new retention applies to reviews from now on; earlier ones keep theirs."""
    user = await _user(session, user_id)
    if data.new_per_day is not None:
        user.practice_new_per_day = data.new_per_day
    if data.desired_retention is not None:
        user.practice_desired_retention = data.desired_retention
    await session.commit()
    return await get_settings(session, user_id=user_id)
