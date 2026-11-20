"""Re-planning: store a new plan version when something changed (decision 0021).

``replan`` is the only writer of plan versions and blocks. Under a per-user advisory lock it:

1. marks the current version's past planned blocks with no linked session as missed;
2. keeps as fixed the current version's planned blocks in the next 24 h that still make
   sense (inside free time, for an upcoming assessment and a unit it still covers);
3. plans again with those fixed blocks through ``preview.build`` (the preview's own code path);
4. writes a new version only if the blocks from now on differ (no churn); otherwise it
   refreshes the current version's report and ``checked_at``.

Done, skipped and missed blocks stay on the version they belong to. Nothing here calls AI.
"""

import uuid
from collections.abc import Mapping
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import exists, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.kinds import REPLAN
from app.jobs.queue import enqueue_replan
from app.models import Assessment, Job, Module, PlanBlock, PlanVersion, StudySession, Topic, User
from app.services.errors import Conflict, NotFound
from app.services.planning import explain
from app.services.planning.availability import Interval
from app.services.planning.inputs import DEFAULT_DAYS, PlanFacts, load_plan_data
from app.services.planning.planner import Block, PlanInput
from app.services.planning.preview import build

FIXED_HOURS = 24
NIGHTLY_HOUR = 3

Key = tuple[datetime, datetime, uuid.UUID, uuid.UUID, uuid.UUID | None, str, str, str, str, str]


async def lock_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Hold the user's re-plan lock until this transaction ends."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:user_id, 0))"),
        {"user_id": str(user_id)},
    )


async def current_version(session: AsyncSession, *, user_id: uuid.UUID) -> PlanVersion | None:
    return await session.scalar(
        select(PlanVersion)
        .where(PlanVersion.user_id == user_id)
        .order_by(PlanVersion.number.desc())
        .limit(1)
    )


async def mark_missed(session: AsyncSession, version: PlanVersion, now: datetime) -> None:
    """Planned blocks that ended with no linked session are missed. A block with a linked
    session is left alone: its session's end marks it done."""
    linked = exists().where(
        StudySession.plan_block_id == PlanBlock.id, StudySession.user_id == PlanBlock.user_id
    )
    await session.execute(
        update(PlanBlock)
        .where(
            PlanBlock.user_id == version.user_id,
            PlanBlock.version_id == version.id,
            PlanBlock.status == "planned",
            PlanBlock.end_at <= now,
            ~linked,
        )
        .values(status="missed", status_changed_at=now)
    )


def _inside(start: datetime, end: datetime, free: tuple[Interval, ...]) -> bool:
    """Whether [start, end) lies in the free time (touching intervals merged)."""
    spans: list[tuple[datetime, datetime]] = []
    for interval in sorted(free, key=lambda i: (i.start, i.end)):
        if spans and interval.start <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], interval.end))
        else:
            spans.append((interval.start, interval.end))
    return any(s <= start and end <= e for s, e in spans)


def _block(row: PlanBlock) -> Block:
    return Block(
        start=row.start_at,
        end=row.end_at,
        module_id=row.module_id,
        assessment_id=row.assessment_id,
        topic_id=row.topic_id,
        kind="review" if row.kind == "review" else "study",
        reason=row.reason,  # type: ignore[arg-type]  # checked by ck_plan_blocks_reason
    )


def _row_key(row: PlanBlock) -> Key:
    return (
        row.start_at,
        row.end_at,
        row.module_id,
        row.assessment_id,
        row.topic_id,
        row.kind,
        row.reason,
        row.method,
        row.reason_text,
        row.method_text,
    )


async def _keepable(
    session: AsyncSession, version: PlanVersion, request: PlanInput, now: datetime
) -> dict[Block, PlanBlock]:
    """The current version's planned blocks in the next 24 h (one in progress included) that
    can stay: inside free time, for an upcoming assessment, and on a unit it still covers."""
    rows = (
        await session.scalars(
            select(PlanBlock).where(
                PlanBlock.user_id == version.user_id,
                PlanBlock.version_id == version.id,
                PlanBlock.status == "planned",
                PlanBlock.end_at > now,
                PlanBlock.start_at < now + timedelta(hours=FIXED_HOURS),
            )
        )
    ).all()
    upcoming = {a.id: a for a in request.assessments}
    units = {t for a in request.assessments for t in a.topic_ids}
    kept: dict[Block, PlanBlock] = {}
    for row in rows:
        if row.assessment_id not in upcoming:
            continue
        if row.topic_id is not None and row.topic_id not in units:
            continue
        if not _inside(row.start_at, row.end_at, request.free):
            continue
        kept[_block(row)] = row
    return kept


async def _summary(
    session: AsyncSession,
    trigger: str,
    detail: Mapping[str, Any],
    facts: PlanFacts,
    *,
    user_id: uuid.UUID,
) -> str:
    """The version's one sentence, with names looked up for this user only."""
    tz = facts.timezone
    block_name: str | None = None
    block_start: datetime | None = None
    assessment: str | None = detail.get("name")
    module: str | None = None
    if "block_id" in detail:
        row = await session.scalar(
            select(PlanBlock).where(
                PlanBlock.id == uuid.UUID(str(detail["block_id"])), PlanBlock.user_id == user_id
            )
        )
        if row is not None:
            block_start = row.start_at
            if row.topic_id is not None:
                topic = await session.scalar(
                    select(Topic).where(Topic.id == row.topic_id, Topic.user_id == user_id)
                )
                block_name = topic.name if topic else None
            else:
                name = await _assessment_name(session, row.assessment_id, user_id=user_id)
                block_name = f"the final review for {name}" if name else None
    if assessment is None and "assessment_id" in detail:
        assessment = await _assessment_name(
            session, uuid.UUID(str(detail["assessment_id"])), user_id=user_id
        )
    if "module_id" in detail:
        module = await session.scalar(
            select(Module.code).where(
                Module.id == uuid.UUID(str(detail["module_id"])), Module.user_id == user_id
            )
        )
    minutes = detail.get("minutes")
    return explain.version_summary(
        trigger,
        timezone=tz,
        block_name=block_name,
        block_start=block_start,
        minutes=int(minutes) if minutes is not None else None,
        assessment=assessment,
        module=module,
    )


async def _assessment_name(
    session: AsyncSession, assessment_id: uuid.UUID, *, user_id: uuid.UUID
) -> str | None:
    found = (
        await session.execute(
            select(Module.code, Assessment.title)
            .join(Module, (Module.id == Assessment.module_id) & (Module.user_id == user_id))
            .where(Assessment.id == assessment_id, Assessment.user_id == user_id)
        )
    ).first()
    return f"{found[0]} {found[1]}" if found else None


async def replan(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    now: datetime,
    trigger: str,
    detail: Mapping[str, Any] | None = None,
) -> PlanVersion:
    """Re-plan for the user (see the module docstring). Commits, which releases the lock."""
    await lock_user(session, user_id)
    current = await current_version(session, user_id=user_id)
    if current is not None:
        await mark_missed(session, current, now)

    data = await load_plan_data(session, user_id=user_id, now=now, days=DEFAULT_DAYS)
    kept = await _keepable(session, current, data.input, now) if current else {}
    request = PlanInput(
        now=data.input.now,
        free=data.input.free,
        daily_cap_minutes=data.input.daily_cap_minutes,
        timezone=data.input.timezone,
        assessments=data.input.assessments,
        topics=data.input.topics,
        studied_minutes=data.input.studied_minutes,
        fixed=tuple(kept),
        studied_on=data.input.studied_on,
    )
    built = build(request, data.facts, now=now, days=DEFAULT_DAYS)
    report = built.preview.feasibility.model_dump(mode="json")

    # Each new block's key; a fixed block keeps the texts it was generated with.
    new: list[tuple[Key, PlanBlock | None]] = []
    for block, out in built.blocks:
        old = kept.get(block)
        if old is not None:
            new.append((_row_key(old), old))
        else:
            key: Key = (
                out.start,
                out.end,
                out.module_id,
                out.assessment_id,
                out.topic_id,
                out.kind,
                out.reason,
                out.method,
                out.reason_text,
                out.method_text,
            )
            new.append((key, None))

    if current is not None:
        rows = (
            await session.scalars(
                select(PlanBlock)
                .where(
                    PlanBlock.user_id == user_id,
                    PlanBlock.version_id == current.id,
                    PlanBlock.status == "planned",
                    PlanBlock.end_at > now,
                )
                .order_by(PlanBlock.start_at, PlanBlock.end_at)
            )
        ).all()
        if sorted(_row_key(r) for r in rows) == sorted(k for k, _ in new):
            current.report = report
            current.checked_at = now
            await session.commit()
            return current

    version = PlanVersion(
        user_id=user_id,
        number=(current.number + 1) if current else 1,
        trigger=trigger,
        summary=await _summary(session, trigger, detail or {}, data.facts, user_id=user_id),
        generated_at=now,
        checked_at=now,
        days=DEFAULT_DAYS,
        report=report,
    )
    session.add(version)
    await session.flush()
    for key, old in new:
        start, end, module_id, assessment_id, topic_id, kind, reason, method, why, how = key
        session.add(
            PlanBlock(
                user_id=user_id,
                version_id=version.id,
                start_at=start,
                end_at=end,
                module_id=module_id,
                assessment_id=assessment_id,
                topic_id=topic_id,
                kind=kind,
                reason=reason,
                method=method,
                reason_text=why,
                method_text=how,
                status="planned",
                fixed=old is not None,
            )
        )
    await session.commit()
    return version


async def skip_block(
    session: AsyncSession, block_id: uuid.UUID, *, user_id: uuid.UUID, now: datetime
) -> PlanVersion:
    """Skip a planned block of the current version and re-plan at once (trigger skip)."""
    await lock_user(session, user_id)
    block = await session.scalar(
        select(PlanBlock).where(PlanBlock.id == block_id, PlanBlock.user_id == user_id)
    )
    if block is None:
        raise NotFound("Plan block")
    current = await current_version(session, user_id=user_id)
    if current is None or block.version_id != current.id or block.status != "planned":
        raise Conflict("Only a planned block of the current plan can be skipped.")
    block.status = "skipped"
    block.status_changed_at = now
    await session.flush()
    return await replan(
        session, user_id=user_id, now=now, trigger="skip", detail={"block_id": str(block_id)}
    )


def last_nightly(now: datetime, timezone: ZoneInfo) -> datetime:
    """The most recent local 03:00 at or before ``now``."""
    local = now.astimezone(timezone)
    day = local.date() if local.time() >= time(NIGHTLY_HOUR) else local.date() - timedelta(days=1)
    return datetime.combine(day, time(NIGHTLY_HOUR), tzinfo=timezone)


async def queue_nightly_replans(session: AsyncSession, now: datetime) -> int:
    """Queue a nightly re-plan for each user whose current version wasn't checked since their
    most recent local 03:00, unless a re-plan is already queued or running. Users with no
    version are skipped. Commits; returns how many were queued."""
    latest = (
        select(PlanVersion.user_id, func.max(PlanVersion.number).label("number"))
        .group_by(PlanVersion.user_id)
        .subquery()
    )
    pending = exists().where(
        Job.user_id == User.id, Job.kind == REPLAN, Job.status.in_(("queued", "running"))
    )
    rows = (
        await session.execute(
            select(User.id, User.timezone, PlanVersion.checked_at)
            .join(latest, latest.c.user_id == User.id)
            .join(
                PlanVersion,
                (PlanVersion.user_id == User.id) & (PlanVersion.number == latest.c.number),
            )
            .where(~pending)
        )
    ).all()
    queued = 0
    for user_id, timezone, checked_at in rows:
        if checked_at < last_nightly(now, ZoneInfo(timezone)):
            await enqueue_replan(session, user_id=user_id, trigger="nightly")
            queued += 1
    await session.commit()
    return queued
