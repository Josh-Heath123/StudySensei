"""The private calendar link and what it serves (decision 0024). Scoped by ``user_id``.

The link's token is 32 random bytes (urlsafe); only its sha256 is stored, and the token is
returned once, when the link is created or reset. A reset replaces the hash, so the old link
stops working. ``GET /calendar/{token}.ics`` finds the user by the hash alone (no session),
which is why it must stay outside any future auth middleware.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Assessment, CalendarFeed, Module, PlanBlock, StudySession, Topic
from app.services.calendar.ics import (
    CalendarEvent,
    build_calendar,
    event_description,
    event_summary,
)
from app.services.errors import NotFound
from app.services.planning.replan import current_version
from app.services.push.payload import slot_key

AHEAD = timedelta(weeks=8)
DONE_BACK = timedelta(days=7)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def get_feed(session: AsyncSession, *, user_id: uuid.UUID) -> CalendarFeed | None:
    return await session.scalar(select(CalendarFeed).where(CalendarFeed.user_id == user_id))


async def create_or_reset(
    session: AsyncSession, *, user_id: uuid.UUID, now: datetime
) -> tuple[str, CalendarFeed]:
    """A new token for the user's link (replacing any old one). Returns the token, once."""
    token = secrets.token_urlsafe(32)
    await session.execute(
        insert(CalendarFeed)
        .values(id=uuid.uuid4(), user_id=user_id, token_hash=token_hash(token), created_at=now)
        .on_conflict_do_update(
            constraint="uq_calendar_feeds_user",
            # A reset is a new link: its creation time and fetches start again.
            set_={
                "token_hash": token_hash(token),
                "created_at": now,
                "last_fetched_at": None,
            },
        )
    )
    await session.commit()
    feed = await get_feed(session, user_id=user_id)
    assert feed is not None
    await session.refresh(feed)
    return token, feed


async def delete_feed(session: AsyncSession, *, user_id: uuid.UUID) -> None:
    deleted = await session.execute(
        delete(CalendarFeed).where(CalendarFeed.user_id == user_id).returning(CalendarFeed.id)
    )
    if deleted.first() is None:
        raise NotFound("Calendar link")
    await session.commit()


async def user_for_token(session: AsyncSession, token: str, *, now: datetime) -> uuid.UUID:
    """The user whose link this is (recording the fetch), or NotFound."""
    feed = await session.scalar(
        select(CalendarFeed).where(CalendarFeed.token_hash == token_hash(token))
    )
    if feed is None:
        raise NotFound("Calendar")
    feed.last_fetched_at = now
    user_id = feed.user_id
    await session.commit()
    return user_id


async def calendar_events(
    session: AsyncSession, *, user_id: uuid.UUID, now: datetime
) -> list[CalendarEvent]:
    """The current version's planned blocks that haven't ended, up to 8 weeks ahead, and done
    blocks of the last 7 days at their measured time (decision 0023), marked "✓ "."""
    names = (
        select(PlanBlock, Module.code, Assessment.title, Topic.name)
        .join(Module, (Module.id == PlanBlock.module_id) & (Module.user_id == user_id))
        .join(
            Assessment,
            (Assessment.id == PlanBlock.assessment_id) & (Assessment.user_id == user_id),
        )
        .outerjoin(Topic, (Topic.id == PlanBlock.topic_id) & (Topic.user_id == user_id))
        .where(PlanBlock.user_id == user_id)
    )
    events: list[CalendarEvent] = []

    def event(
        block: PlanBlock,
        code: str,
        title: str,
        topic: str | None,
        start: datetime,
        end: datetime,
        *,
        done: bool,
    ) -> CalendarEvent:
        # The slot as shown: a done block's measured times, so it never shares a UID with the
        # block the finish re-plan put in its old slot.
        key = slot_key(start, end, block.assessment_id, block.topic_id)
        return CalendarEvent(
            uid=f"{key}@studysensei",
            start=start,
            end=end,
            summary=event_summary(
                topic_name=topic, module_code=code, assessment_title=title, done=done
            ),
            description=event_description(
                method_text=block.method_text, reason_text=block.reason_text
            ),
        )

    version = await current_version(session, user_id=user_id)
    if version is not None:
        planned = await session.execute(
            names.where(
                PlanBlock.version_id == version.id,
                PlanBlock.status == "planned",
                PlanBlock.end_at > now,
                PlanBlock.start_at < now + AHEAD,
            )
        )
        for block, code, title, topic in planned:
            events.append(
                event(block, code, title, topic, block.start_at, block.end_at, done=False)
            )

    studied = await session.execute(
        names.add_columns(StudySession.started_at, StudySession.ended_at)
        .join(
            StudySession,
            (StudySession.plan_block_id == PlanBlock.id) & (StudySession.user_id == user_id),
        )
        .where(
            PlanBlock.status == "done",
            StudySession.ended_at.is_not(None),
            StudySession.ended_at > now - DONE_BACK,
            StudySession.started_at <= now,
        )
    )
    for block, code, title, topic, started, ended in studied.all():
        assert ended is not None
        events.append(event(block, code, title, topic, started, ended, done=True))
    # One event per UID (a block studied twice keeps its latest session).
    unique = {e.uid: e for e in events}
    return sorted(unique.values(), key=lambda e: (e.start, e.uid))


async def calendar_file(session: AsyncSession, *, user_id: uuid.UUID, now: datetime) -> bytes:
    return build_calendar(await calendar_events(session, user_id=user_id, now=now), now=now)
