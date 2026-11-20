"""Reading the stored plan (decision 0021): the current version and its blocks, with names.
Scoped by ``user_id``. ``plan_for`` is the one read with a side effect: with no version yet,
it re-plans to create version 1 (trigger initial)."""

import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Assessment, Module, PlanBlock, PlanVersion, Topic
from app.schemas.planning import (
    MAX_RANGE_DAYS,
    FeasibilityOut,
    PlanOut,
    PlanVersionOut,
    StoredBlockOut,
)
from app.services.errors import Invalid
from app.services.planning import store
from app.services.planning.availability import MINUTES_PER_DAY, local_to_utc
from app.services.planning.replan import current_version, replan

DEFAULT_RANGE_DAYS = 7


async def version_out(session: AsyncSession, version: PlanVersion) -> PlanVersionOut:
    user = await store.get_settings(session, user_id=version.user_id)
    return PlanVersionOut(
        number=version.number,
        trigger=version.trigger,
        summary=version.summary,
        generated_at=version.generated_at,
        checked_at=version.checked_at,
        timezone=user.timezone,
        days=version.days,
        report=FeasibilityOut.model_validate(version.report),
    )


async def _blocks(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    where: list[ColumnElement[bool]],
    limit: int | None = None,
) -> list[StoredBlockOut]:
    query = (
        select(PlanBlock, Module.code, Module.colour, Assessment.title, Topic.name)
        .join(Module, (Module.id == PlanBlock.module_id) & (Module.user_id == user_id))
        .join(
            Assessment,
            (Assessment.id == PlanBlock.assessment_id) & (Assessment.user_id == user_id),
        )
        .outerjoin(Topic, (Topic.id == PlanBlock.topic_id) & (Topic.user_id == user_id))
        .where(PlanBlock.user_id == user_id, *where)
        .order_by(PlanBlock.start_at, PlanBlock.end_at)
    )
    if limit is not None:
        query = query.limit(limit)
    out = []
    for block, code, colour, title, topic_name in await session.execute(query):
        out.append(
            StoredBlockOut(
                id=block.id,
                start=block.start_at,
                end=block.end_at,
                minutes=int((block.end_at - block.start_at).total_seconds() // 60),
                module_id=block.module_id,
                module_code=code,
                module_colour=colour,
                assessment_id=block.assessment_id,
                assessment_title=title,
                topic_id=block.topic_id,
                topic_name=topic_name,
                kind=block.kind,
                reason=block.reason,
                method=block.method,
                reason_text=block.reason_text,
                method_text=block.method_text,
                status=block.status,
                status_changed_at=block.status_changed_at,
                fixed=block.fixed,
            )
        )
    return out


async def ensure_version(
    session: AsyncSession, *, user_id: uuid.UUID, now: datetime
) -> PlanVersion:
    """The current version, creating version 1 (trigger initial) when there's none."""
    found = await current_version(session, user_id=user_id)
    if found is not None:
        return found
    return await replan(session, user_id=user_id, now=now, trigger="initial")


async def plan_for(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    now: datetime,
    first: date | None = None,
    last: date | None = None,
) -> PlanOut:
    """The current version and its blocks overlapping the local dates ``first`` to ``last``
    (default today to 7 days on; at most 62 days)."""
    version = await ensure_version(session, user_id=user_id, now=now)
    head = await version_out(session, version)
    tz = ZoneInfo(head.timezone)
    first = first or now.astimezone(tz).date()
    last = last or first + timedelta(days=DEFAULT_RANGE_DAYS)
    if last < first:
        raise Invalid("The range ends before it starts.")
    if last - first >= timedelta(days=MAX_RANGE_DAYS):
        raise Invalid(f"Ask for at most {MAX_RANGE_DAYS} days at a time.")
    start, end = local_to_utc(first, 0, tz), local_to_utc(last, MINUTES_PER_DAY, tz)
    blocks = await _blocks(
        session,
        user_id=user_id,
        where=[
            PlanBlock.version_id == version.id,
            PlanBlock.end_at > start,
            PlanBlock.start_at < end,
        ],
    )
    return PlanOut(**head.model_dump(), first=first, last=last, blocks=blocks)


async def next_block(
    session: AsyncSession, *, user_id: uuid.UUID, now: datetime
) -> StoredBlockOut | None:
    """The current version's next planned block that hasn't ended (one in progress counts)."""
    version = await current_version(session, user_id=user_id)
    if version is None:
        return None
    found = await _blocks(
        session,
        user_id=user_id,
        where=[
            PlanBlock.version_id == version.id,
            PlanBlock.status == "planned",
            PlanBlock.end_at > now,
        ],
        limit=1,
    )
    return found[0] if found else None
