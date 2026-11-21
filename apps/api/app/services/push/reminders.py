"""Queueing push reminders (decision 0024). The worker calls ``queue_reminders`` once a minute.

For each user with ``reminder_minutes`` set and at least one push subscription: the current
plan version's planned blocks that start in (now, now + reminder_minutes], with no linked
session and whose slot hasn't been reminded. Each gets a ``reminders_sent`` row (ON CONFLICT
DO NOTHING, so two workers can't both send it) and a ``push_reminder`` job in the same
transaction; the job sends to every subscription the user has.

The slot (``payload.slot_key``) is the block's start, end, assessment and topic, not its id, so
a block carried into a new version unchanged isn't reminded twice, and one that moved or was
placed again is.
"""

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.kinds import PUSH_REMINDER
from app.jobs.queue import enqueue
from app.models import (
    Assessment,
    Module,
    PlanBlock,
    PlanVersion,
    PushSubscription,
    ReminderSent,
    StudySession,
    Topic,
    User,
)
from app.services.push.payload import reminder_payload, slot_key
from app.services.push.sender import push_enabled


async def queue_reminders(session: AsyncSession, now: datetime) -> int:
    """Queue a reminder for each block that's due one (see the module docstring). Returns
    how many were queued. Nothing is queued while push is disabled."""
    if not push_enabled():
        return 0
    users = (
        await session.execute(
            select(User.id, User.timezone, User.reminder_minutes).where(
                User.reminder_minutes.is_not(None),
                exists().where(PushSubscription.user_id == User.id),
            )
        )
    ).all()
    queued = 0
    for user_id, timezone, lead in users:
        assert lead is not None
        queued += await _queue_for(session, user_id, ZoneInfo(timezone), lead, now)
    await session.commit()
    return queued


async def _queue_for(
    session: AsyncSession, user_id: uuid.UUID, tz: ZoneInfo, lead: int, now: datetime
) -> int:
    latest = (
        select(func.max(PlanVersion.number)).where(PlanVersion.user_id == user_id).scalar_subquery()
    )
    current = select(PlanVersion.id).where(
        PlanVersion.user_id == user_id, PlanVersion.number == latest
    )
    rows = (
        await session.execute(
            select(PlanBlock, Module.code, Assessment.title, Topic.name)
            .join(Module, (Module.id == PlanBlock.module_id) & (Module.user_id == user_id))
            .join(
                Assessment,
                (Assessment.id == PlanBlock.assessment_id) & (Assessment.user_id == user_id),
            )
            .outerjoin(Topic, (Topic.id == PlanBlock.topic_id) & (Topic.user_id == user_id))
            .where(
                PlanBlock.user_id == user_id,
                PlanBlock.version_id.in_(current),
                PlanBlock.status == "planned",
                PlanBlock.start_at > now,
                PlanBlock.start_at <= now + timedelta(minutes=lead),
                ~exists().where(
                    StudySession.user_id == user_id, StudySession.plan_block_id == PlanBlock.id
                ),
            )
            .order_by(PlanBlock.start_at)
        )
    ).all()
    queued = 0
    for block, code, title, topic_name in rows:
        key = slot_key(block.start_at, block.end_at, block.assessment_id, block.topic_id)
        inserted = await session.scalar(
            insert(ReminderSent)
            .values(id=uuid.uuid4(), user_id=user_id, slot_key=key, sent_at=now)
            .on_conflict_do_nothing(constraint="uq_reminders_sent_user_slot")
            .returning(ReminderSent.id)
        )
        if inserted is None:
            continue  # already reminded (this slot, in this or an earlier version)
        minutes = int((block.end_at - block.start_at).total_seconds() // 60)
        payload = reminder_payload(
            topic_name=topic_name,
            assessment_name=f"{code} {title}",
            start=block.start_at,
            minutes=minutes,
            method_text=block.method_text,
            timezone=tz,
            tag=key,
        )
        # The job works out the TTL when it sends, from the block's start (a reminder that
        # arrives after its block has started is no use).
        enqueue(
            session,
            PUSH_REMINDER,
            {"payload": payload, "slot_key": key, "start_at": block.start_at.isoformat()},
            user_id=user_id,
            max_attempts=1,
        )
        queued += 1
    return queued
