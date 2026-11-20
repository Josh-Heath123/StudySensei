"""Reading the stored plan (decisions 0021 and 0022): the current version and its blocks, with
names, the history (done, skipped and missed blocks of any version), each block's derived
status and the actions the student can take. Scoped by ``user_id``.

``plan_for`` is the one read with a side effect: with no version yet, it re-plans to create
version 1 (trigger initial). Otherwise reading writes nothing: a current planned block that
ended with no session is *reported* as missed (``replan.unattended``, the predicate
``mark_missed`` uses) and stored as missed by the next re-plan.
"""

import math
import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.kinds import REPLAN
from app.models import Assessment, Job, Module, PlanBlock, PlanVersion, StudySession, Topic
from app.schemas.planning import (
    MAX_RANGE_DAYS,
    BlockActionsOut,
    FeasibilityOut,
    PlanOut,
    PlanVersionOut,
    StoredBlockOut,
)
from app.services.errors import Invalid
from app.services.planning import store
from app.services.planning.availability import MINUTES_PER_DAY, local_to_utc
from app.services.planning.replan import current_version, replan, unattended

DEFAULT_RANGE_DAYS = 7
HISTORY = ("done", "skipped", "missed")
NO_ACTIONS = BlockActionsOut(start=False, skip=False, move=False)


def shown_times(
    block: PlanBlock, status: str, linked: StudySession | None
) -> tuple[datetime, datetime]:
    """When a block is shown: a done block at its linked session's measured start and end
    (decision 0023: one done early mustn't sit under the block that re-used its slot),
    anything else at the plan's times."""
    if status == "done" and linked is not None and linked.ended_at is not None:
        return linked.started_at, linked.ended_at
    return block.start_at, block.end_at


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


async def replan_pending(session: AsyncSession, *, user_id: uuid.UUID) -> bool:
    """Whether a re-plan job is queued or running for the user."""
    found = await session.scalar(
        select(Job.id)
        .where(Job.user_id == user_id, Job.kind == REPLAN, Job.status.in_(("queued", "running")))
        .limit(1)
    )
    return found is not None


async def blocks_out(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    now: datetime,
    current: PlanVersion | None,
    where: list[ColumnElement[bool]],
    limit: int | None = None,
    window: tuple[datetime, datetime] | None = None,
) -> list[StoredBlockOut]:
    """Blocks matching ``where`` with their names, linked session, derived status and actions:
    the one code path behind ``GET /plan`` and ``GET /plan/next``. With ``window``, only
    blocks whose shown times (``shown_times``) overlap it, ordered by those times."""
    query = (
        select(
            PlanBlock,
            Module.code,
            Module.colour,
            Assessment.title,
            Topic.name,
            unattended(now).label("unattended"),
        )
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
    rows = (await session.execute(query)).all()

    # Each block's latest linked session, and whether any session is open at all.
    linked: dict[uuid.UUID, StudySession] = {}
    if rows:
        for study in await session.scalars(
            select(StudySession)
            .where(
                StudySession.user_id == user_id,
                StudySession.plan_block_id.in_([r[0].id for r in rows]),
            )
            .order_by(StudySession.started_at)
        ):
            if study.plan_block_id is not None:
                linked[study.plan_block_id] = study
    open_any = (
        await session.scalar(
            select(StudySession.id)
            .where(StudySession.user_id == user_id, StudySession.ended_at.is_(None))
            .limit(1)
        )
        is not None
    )

    out = []
    for block, code, colour, title, topic_name, missed in rows:
        in_current = current is not None and block.version_id == current.id
        status = "missed" if in_current and missed else block.status
        found = linked.get(block.id)
        start, end = shown_times(block, status, found)
        if window is not None and not (end > window[0] and start < window[1]):
            continue
        actions = NO_ACTIONS
        if in_current and status == "planned":
            open_linked = found is not None and found.ended_at is None
            actions = BlockActionsOut(
                start=block.end_at > now and not open_any,
                skip=not open_linked,
                move=block.start_at > now and found is None,
            )
        out.append(
            StoredBlockOut(
                id=block.id,
                start=start,
                end=end,
                minutes=int((end - start).total_seconds() // 60),
                planned_start=block.start_at,
                planned_end=block.end_at,
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
                status=status,
                status_changed_at=block.status_changed_at,
                fixed=block.fixed,
                pinned=block.pinned,
                linked_session_id=found.id if found else None,
                session_minutes=(
                    math.floor(found.active_seconds / 60)
                    if found is not None and status == "done"
                    else None
                ),
                actions=actions,
            )
        )
    out.sort(key=lambda b: (b.start, b.end))
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
    """The current version, its blocks overlapping the local dates ``first`` to ``last``
    (default today to 7 days on; at most 62 days), and the history in that range: done,
    skipped and missed blocks of any version. Superseded planned rows are never returned."""
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
    # A done block shows at its session's time, which may be outside its planned range.
    studied_in_range = select(StudySession.plan_block_id).where(
        StudySession.user_id == user_id,
        StudySession.plan_block_id.is_not(None),
        StudySession.ended_at > start,
        StudySession.started_at < end,
    )
    blocks = await blocks_out(
        session,
        user_id=user_id,
        now=now,
        current=version,
        where=[
            (PlanBlock.version_id == version.id) | PlanBlock.status.in_(HISTORY),
            or_(
                (PlanBlock.end_at > start) & (PlanBlock.start_at < end),
                PlanBlock.id.in_(studied_in_range),
            ),
        ],
        window=(start, end),
    )
    return PlanOut(
        **head.model_dump(),
        first=first,
        last=last,
        blocks=blocks,
        replan_pending=await replan_pending(session, user_id=user_id),
    )


async def next_block(
    session: AsyncSession, *, user_id: uuid.UUID, now: datetime
) -> StoredBlockOut | None:
    """The current version's next planned block that hasn't ended (one in progress counts)."""
    version = await current_version(session, user_id=user_id)
    if version is None:
        return None
    found = await blocks_out(
        session,
        user_id=user_id,
        now=now,
        current=version,
        where=[
            PlanBlock.version_id == version.id,
            PlanBlock.status == "planned",
            PlanBlock.end_at > now,
        ],
        limit=1,
    )
    return found[0] if found else None
