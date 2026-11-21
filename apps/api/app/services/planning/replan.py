"""Re-planning: store a new plan version when something changed (decision 0021).

``replan`` is the only writer of plan versions and blocks. Under a per-user advisory lock it:

1. marks the current version's past planned blocks with no linked session as missed;
2. keeps as fixed the current version's planned blocks in the next 24 h that still make
   sense (inside free time, for an upcoming assessment and a unit it still covers), and
   takes the time of skipped blocks that haven't ended out of the free time;
3. plans again with those fixed blocks through ``preview.build`` (the preview's own code path);
4. writes a new version only if the blocks from now on, or the assessments covered,
   differ (no churn); otherwise it refreshes the current version's report and ``checked_at``.

Done, skipped and missed blocks stay on the version they belong to. Nothing here calls AI.
"""

import uuid
from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, exists, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.kinds import REPLAN
from app.jobs.queue import enqueue_replan
from app.models import Assessment, Job, Module, PlanBlock, PlanVersion, StudySession, Topic, User
from app.services.errors import Conflict, Invalid, NotFound
from app.services.planning import explain
from app.services.planning.availability import Interval
from app.services.planning.inputs import DEFAULT_DAYS, PlanFacts, load_plan_data
from app.services.planning.moves import check_move
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


def unattended(now: datetime) -> ColumnElement[bool]:
    """A planned block that ended with no linked session: missed. The one predicate for
    ``mark_missed`` and for the status ``GET /plan`` derives without writing (decision 0022)."""
    linked = exists().where(
        StudySession.plan_block_id == PlanBlock.id, StudySession.user_id == PlanBlock.user_id
    )
    return (PlanBlock.status == "planned") & (PlanBlock.end_at <= now) & ~linked


async def mark_missed(session: AsyncSession, version: PlanVersion, now: datetime) -> None:
    """Planned blocks that ended with no linked session are missed. A block with a linked
    session is left alone: its session's end marks it done."""
    await session.execute(
        update(PlanBlock)
        .where(
            PlanBlock.user_id == version.user_id,
            PlanBlock.version_id == version.id,
            unattended(now),
        )
        .values(status="missed", status_changed_at=now)
    )


async def has_open_session(session: AsyncSession, block: PlanBlock) -> bool:
    """Whether a session linked to ``block`` hasn't ended."""
    found = await session.scalar(
        select(StudySession.id).where(
            StudySession.user_id == block.user_id,
            StudySession.plan_block_id == block.id,
            StudySession.ended_at.is_(None),
        )
    )
    return found is not None


def _inside(start: datetime, end: datetime, free: tuple[Interval, ...]) -> bool:
    """Whether [start, end) lies in the free time (touching intervals merged)."""
    spans: list[tuple[datetime, datetime]] = []
    for interval in sorted(free, key=lambda i: (i.start, i.end)):
        if spans and interval.start <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], interval.end))
        else:
            spans.append((interval.start, interval.end))
    return any(s <= start and end <= e for s, e in spans)


def without(
    free: tuple[Interval, ...], busy: list[tuple[datetime, datetime]]
) -> tuple[Interval, ...]:
    """The free time with the busy stretches cut out."""
    out: list[Interval] = []
    for interval in free:
        pieces = [(interval.start, interval.end)]
        for start, end in busy:
            pieces = [
                part
                for s, e in pieces
                for part in ((s, min(e, start)), (max(s, end), e))
                if part[1] > part[0]
            ]
        out.extend(Interval(s, e) for s, e in pieces)
    return tuple(out)


async def _skipped(
    session: AsyncSession, user_id: uuid.UUID, now: datetime
) -> list[tuple[datetime, datetime]]:
    """The times of skipped blocks (any version) that haven't ended: the student said they
    can't study then, so nothing new goes there."""
    rows = await session.execute(
        select(PlanBlock.start_at, PlanBlock.end_at).where(
            PlanBlock.user_id == user_id, PlanBlock.status == "skipped", PlanBlock.end_at > now
        )
    )
    return [(start, end) for start, end in rows]


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
    """The current version's planned blocks that haven't ended and start in the next 24 h (one
    in progress included), or that the student pinned by moving them (any time; decision 0022),
    and can stay: inside free time, for an upcoming assessment, and on a unit it still covers.
    An invalid pinned block is dropped, and its unit's time is placed again."""
    rows = (
        await session.scalars(
            select(PlanBlock).where(
                PlanBlock.user_id == version.user_id,
                PlanBlock.version_id == version.id,
                PlanBlock.status == "planned",
                PlanBlock.end_at > now,
                (PlanBlock.start_at < now + timedelta(hours=FIXED_HOURS)) | PlanBlock.pinned,
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
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
) -> str:
    """The version's one sentence, with names looked up for this user only. For a skip,
    ``before`` and ``after`` (the previous and new reports) say whether the skipped block's
    assessment is now shorter."""
    tz = facts.timezone
    block_name: str | None = None
    block_start: datetime | None = None
    short_now: int | None = None
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
            if trigger == "skip" and before is not None and after is not None:
                grown = _short(after, row.assessment_id) - _short(before, row.assessment_id)
                if grown > 0:
                    short_now = _short(after, row.assessment_id)
                    assessment = await _assessment_name(session, row.assessment_id, user_id=user_id)
            if row.topic_id is not None:
                topic = await session.scalar(
                    select(Topic).where(Topic.id == row.topic_id, Topic.user_id == user_id)
                )
                block_name = topic.name if topic else None
            else:
                name = await _assessment_name(session, row.assessment_id, user_id=user_id)
                block_name = f"the final review for {name}" if name else None
    assessment_deleted = False
    if "assessment_id" in detail:
        found = await _assessment_name(
            session, uuid.UUID(str(detail["assessment_id"])), user_id=user_id
        )
        # The name was stored with the trigger, so a deleted one can still be named.
        assessment_deleted = trigger == "assessment" and found is None
        if assessment is None:
            assessment = found
    if "module_id" in detail:
        module = await session.scalar(
            select(Module.code).where(
                Module.id == uuid.UUID(str(detail["module_id"])), Module.user_id == user_id
            )
        )
    minutes = detail.get("minutes")
    moved_to = datetime.fromisoformat(str(detail["to"])) if "to" in detail else None
    return explain.version_summary(
        trigger,
        timezone=tz,
        block_name=block_name,
        block_start=block_start,
        minutes=int(minutes) if minutes is not None else None,
        assessment=assessment,
        module=module,
        short_now=short_now,
        moved_to=moved_to,
        assessment_deleted=assessment_deleted,
    )


def _assessment_ids(report: Mapping[str, Any]) -> set[str]:
    """The assessments a stored report covers (planned ones and those beyond its days)."""
    return {
        str(entry.get("assessment_id"))
        for part in ("assessments", "later")
        for entry in report.get(part, [])
    }


def _short(report: Mapping[str, Any], assessment_id: uuid.UUID) -> int:
    """An assessment's short minutes in a stored report (0 if it isn't there)."""
    for entry in report.get("assessments", []):
        if entry.get("assessment_id") == str(assessment_id):
            return int(entry.get("short_minutes", 0))
    return 0


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
    moved: Mapping[uuid.UUID, datetime] | None = None,
) -> PlanVersion:
    """Re-plan for the user (see the module docstring). Commits, which releases the lock.
    ``moved`` maps a block of the current version to its new start: it's carried at that time
    and pinned, with its texts kept (decision 0022)."""
    await lock_user(session, user_id)
    current = await current_version(session, user_id=user_id)
    if current is not None:
        await mark_missed(session, current, now)

    data = await load_plan_data(session, user_id=user_id, now=now, days=DEFAULT_DAYS)
    kept = await _keepable(session, current, data.input, now) if current else {}
    pinned_ids: set[uuid.UUID] = set()
    for block_id, start in (moved or {}).items():
        row = await session.scalar(
            select(PlanBlock).where(PlanBlock.id == block_id, PlanBlock.user_id == user_id)
        )
        if row is None:
            continue
        kept = {b: r for b, r in kept.items() if r.id != row.id}
        at = _block(row)
        kept[replace(at, start=start, end=start + (at.end - at.start))] = row
        pinned_ids.add(row.id)
    request = PlanInput(
        now=data.input.now,
        free=without(data.input.free, await _skipped(session, user_id, now)),
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
            # Its texts as generated; its time as carried (moved, or the same).
            new.append(((block.start, block.end, *_row_key(old)[2:]), old))
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
        # Equal blocks and the same assessments: nothing to say. (Deleting an assessment
        # cascades its blocks away, so the blocks alone can look unchanged; decision 0023.)
        if sorted(_row_key(r) for r in rows) == sorted(k for k, _ in new) and _assessment_ids(
            current.report
        ) == _assessment_ids(report):
            current.report = report
            current.checked_at = now
            await session.commit()
            return current

    version = PlanVersion(
        user_id=user_id,
        number=(current.number + 1) if current else 1,
        trigger=trigger,
        # Version 1 is "Your first plan.", whatever triggered it (decision 0022).
        summary="Your first plan."
        if current is None
        else await _summary(
            session,
            trigger,
            detail or {},
            data.facts,
            user_id=user_id,
            before=current.report if current else None,
            after=report,
        ),
        generated_at=now,
        checked_at=now,
        days=DEFAULT_DAYS,
        report=report,
    )
    session.add(version)
    await session.flush()
    for key, old in new:
        start, end, module_id, assessment_id, topic_id, kind, reason, method, why, how = key
        row = PlanBlock(
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
            pinned=old is not None and (old.pinned or old.id in pinned_ids),
        )
        session.add(row)
        if old is not None:
            # A session started on the old row follows its block to the copy (decision 0022).
            await session.flush()
            await session.execute(
                update(StudySession)
                .where(StudySession.user_id == user_id, StudySession.plan_block_id == old.id)
                .values(plan_block_id=row.id)
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
    if await has_open_session(session, block):
        raise Conflict("Its session is still open.")
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
    most recent local 03:00, unless a re-plan is already queued or running, or one failed
    since that 03:00 (so a failing re-plan isn't retried every minute; decision 0022). Users
    with no version are skipped. Commits; returns how many were queued."""
    latest = (
        select(PlanVersion.user_id, func.max(PlanVersion.number).label("number"))
        .group_by(PlanVersion.user_id)
        .subquery()
    )
    pending = exists().where(
        Job.user_id == User.id, Job.kind == REPLAN, Job.status.in_(("queued", "running"))
    )
    failed = (
        select(Job.user_id, func.max(Job.finished_at).label("failed_at"))
        .where(Job.kind == REPLAN, Job.status == "failed")
        .group_by(Job.user_id)
        .subquery()
    )
    rows = (
        await session.execute(
            select(User.id, User.timezone, PlanVersion.checked_at, failed.c.failed_at)
            .join(latest, latest.c.user_id == User.id)
            .outerjoin(failed, failed.c.user_id == User.id)
            .join(
                PlanVersion,
                (PlanVersion.user_id == User.id) & (PlanVersion.number == latest.c.number),
            )
            .where(~pending)
        )
    ).all()
    queued = 0
    for user_id, timezone, checked_at, failed_at in rows:
        night = last_nightly(now, ZoneInfo(timezone))
        if failed_at is not None and failed_at >= night:
            continue
        if checked_at < night:
            await enqueue_replan(session, user_id=user_id, trigger="nightly")
            queued += 1
    await session.commit()
    return queued


async def move_block(
    session: AsyncSession,
    block_id: uuid.UUID,
    start: datetime,
    *,
    user_id: uuid.UUID,
    now: datetime,
) -> PlanVersion:
    """Move a planned block of the current version that hasn't started and has no linked
    session to ``start`` (decision 0022), then re-plan inline (trigger move) with it pinned
    there. ``Invalid`` with the sentence if the move breaks a rule (``moves.py``)."""
    await lock_user(session, user_id)
    block = await session.scalar(
        select(PlanBlock).where(PlanBlock.id == block_id, PlanBlock.user_id == user_id)
    )
    if block is None:
        raise NotFound("Plan block")
    current = await current_version(session, user_id=user_id)
    if current is None or block.version_id != current.id or block.status != "planned":
        raise Conflict("Only a planned block of the current plan can be moved.")
    if block.start_at <= now:
        raise Conflict("It has already started.")
    linked = await session.scalar(
        select(StudySession.id).where(
            StudySession.user_id == user_id, StudySession.plan_block_id == block.id
        )
    )
    if linked is not None:
        raise Conflict("It has a session.")

    data = await load_plan_data(session, user_id=user_id, now=now, days=DEFAULT_DAYS)
    others = (
        await session.scalars(
            select(PlanBlock).where(
                PlanBlock.user_id == user_id,
                PlanBlock.version_id == current.id,
                PlanBlock.id != block.id,
                PlanBlock.status.in_(("planned", "done")),
            )
        )
    ).all()
    due_at = await session.scalar(
        select(Assessment.due_at).where(
            Assessment.id == block.assessment_id, Assessment.user_id == user_id
        )
    )
    problem = check_move(
        _block(block),
        start,
        now=now,
        free=without(data.input.free, await _skipped(session, user_id, now)),
        neighbours=[_block(r) for r in others],
        booked=[_block(r) for r in others if r.status == "planned"],
        due_at=due_at or block.end_at,
        daily_cap_minutes=data.input.daily_cap_minutes,
        studied_on=data.input.studied_on,
        timezone=data.input.timezone,
    )
    if problem is not None:
        name = await _assessment_name(session, block.assessment_id, user_id=user_id)
        raise Invalid(
            explain.move_problem_text(
                problem,
                assessment=name,
                cap=data.input.daily_cap_minutes,
                timezone=data.input.timezone,
            )
        )
    return await replan(
        session,
        user_id=user_id,
        now=now,
        trigger="move",
        detail={"block_id": str(block.id), "to": start.isoformat()},
        moved={block.id: start},
    )
