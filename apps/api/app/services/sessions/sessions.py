import uuid
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SessionEvent, SessionTopicRating, StudySession, Topic
from app.schemas.sessions import EventBatch, EventIn, ReflectionIn, SessionStart
from app.services.academics.modules import get_module
from app.services.academics.topics import get_topic
from app.services.errors import Conflict, Invalid, NotFound
from app.services.sessions.timeline import Event, EventType, Timeline, replay

# How far ahead of the server clock an event may be (device clocks drift).
CLOCK_TOLERANCE = timedelta(minutes=5)


async def get_study_session(
    session: AsyncSession,
    session_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
    for_update: bool = False,
) -> StudySession:
    query = select(StudySession).where(
        StudySession.id == session_id, StudySession.user_id == user_id
    )
    if for_update:
        query = query.with_for_update()
    study = await session.scalar(query)
    if study is None:
        raise NotFound("Session")
    return study


async def get_active_session(session: AsyncSession, *, user_id: uuid.UUID) -> StudySession | None:
    """The user's open (not ended) session, if any. There's at most one."""
    return await session.scalar(
        select(StudySession).where(StudySession.user_id == user_id, StudySession.ended_at.is_(None))
    )


async def list_module_sessions(
    session: AsyncSession,
    module_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
    limit: int,
    offset: int = 0,
) -> tuple[list[StudySession], int]:
    """A page of the module's sessions: the open one first, then newest first. Also the total."""
    await get_module(session, module_id, user_id=user_id)
    mine = (StudySession.user_id == user_id, StudySession.module_id == module_id)
    total = await session.scalar(select(func.count()).select_from(StudySession).where(*mine))
    result = await session.scalars(
        select(StudySession)
        .where(*mine)
        .order_by(
            StudySession.ended_at.is_(None).desc(),
            StudySession.started_at.desc(),
            StudySession.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    return list(result), total or 0


@dataclass(frozen=True)
class ModuleSessionTotals:
    session_count: int
    active_seconds: float
    week_active_seconds: float


async def module_session_totals(
    session: AsyncSession, module_id: uuid.UUID, *, user_id: uuid.UUID, week_start: datetime
) -> ModuleSessionTotals:
    """Measured study time for a module: all time, and for sessions started since `week_start`.

    An open session counts up to its last event (the cached totals); a session that
    started before `week_start` counts wholly in the earlier week.
    """
    await get_module(session, module_id, user_id=user_id)
    this_week = StudySession.started_at >= week_start
    row = (
        await session.execute(
            select(
                func.count(),
                func.coalesce(func.sum(StudySession.active_seconds), 0.0),
                func.coalesce(func.sum(StudySession.active_seconds).filter(this_week), 0.0),
            ).where(StudySession.user_id == user_id, StudySession.module_id == module_id)
        )
    ).one()
    return ModuleSessionTotals(
        session_count=int(row[0]), active_seconds=float(row[1]), week_active_seconds=float(row[2])
    )


async def events_of(
    session: AsyncSession, session_id: uuid.UUID, *, user_id: uuid.UUID
) -> list[SessionEvent]:
    """The session's events in timeline order."""
    result = await session.scalars(
        select(SessionEvent)
        .where(SessionEvent.user_id == user_id, SessionEvent.session_id == session_id)
        .order_by(SessionEvent.occurred_at, SessionEvent.seq)
    )
    return list(result)


async def ratings_for(
    session: AsyncSession, session_ids: Collection[uuid.UUID], *, user_id: uuid.UUID
) -> dict[uuid.UUID, list[SessionTopicRating]]:
    """Topic confidence ratings for each of the given sessions."""
    by_session: dict[uuid.UUID, list[SessionTopicRating]] = {id_: [] for id_ in session_ids}
    if not session_ids:
        return by_session
    result = await session.scalars(
        select(SessionTopicRating)
        .join(StudySession, StudySession.id == SessionTopicRating.session_id)
        .where(StudySession.user_id == user_id, SessionTopicRating.session_id.in_(session_ids))
        .order_by(SessionTopicRating.topic_id)
    )
    for rating in result:
        by_session[rating.session_id].append(rating)
    return by_session


def _check_not_future(times: Iterable[datetime]) -> None:
    limit = datetime.now(UTC) + CLOCK_TOLERANCE
    if any(time > limit for time in times):
        raise Invalid("An event is in the future; check the device clock")


def _as_event(row: SessionEvent) -> Event:
    return Event(cast(EventType, row.type), row.occurred_at, row.seq)


def _apply(study: StudySession, timeline: Timeline) -> None:
    """Copy the replayed state and totals onto the session (a cache of the events)."""
    study.state = timeline.state
    study.started_at = timeline.started_at
    study.ended_at = timeline.ended_at
    study.last_event_at = timeline.last_event_at
    study.active_seconds = timeline.active_seconds
    study.break_seconds = timeline.break_seconds


async def start_session(
    session: AsyncSession, data: SessionStart, *, user_id: uuid.UUID
) -> tuple[StudySession, bool]:
    """Open a session with its start event. Returns (session, created).

    Resending the same start (same event id and details) returns the session it
    already created, so a retried request never opens a second one.
    """
    start = data.start
    stored = await session.scalar(
        select(SessionEvent).where(SessionEvent.user_id == user_id, SessionEvent.id == start.id)
    )
    if stored is not None:
        study = await get_study_session(session, stored.session_id, user_id=user_id)
        same = (
            stored.type == "start"
            and stored.occurred_at == start.occurred_at
            and (study.module_id, study.topic_id) == (data.module_id, data.topic_id)
        )
        if not same:
            raise Conflict("That event id was already used for something else")
        return study, False

    await get_module(session, data.module_id, user_id=user_id)
    if data.topic_id is not None:
        topic = await get_topic(session, data.topic_id, user_id=user_id)
        if topic.module_id != data.module_id:
            raise Invalid("A session's topic must be in its module")
    _check_not_future([start.occurred_at])

    timeline = replay([Event("start", start.occurred_at, 0)])
    study = StudySession(user_id=user_id, module_id=data.module_id, topic_id=data.topic_id)
    _apply(study, timeline)
    try:
        async with session.begin_nested():
            session.add(study)
            await session.flush()
            session.add(
                SessionEvent(
                    user_id=user_id,
                    id=start.id,
                    session_id=study.id,
                    type="start",
                    occurred_at=start.occurred_at,
                )
            )
            await session.flush()
    except IntegrityError as exc:
        if "uq_study_sessions_one_active" not in str(exc.orig):
            raise
        raise Conflict("Another session is still open; end it first") from exc
    await session.commit()
    return study, True


def _dedupe_batch(events: list[EventIn]) -> dict[uuid.UUID, EventIn]:
    """Collapse repeats of the same event within one batch (keeping the posted order)."""
    unique: dict[uuid.UUID, EventIn] = {}
    for event in events:
        seen = unique.setdefault(event.id, event)
        if (seen.type, seen.occurred_at) != (event.type, event.occurred_at):
            raise Conflict(f"Event {event.id} appears twice with different details")
    return unique


async def add_events(
    session: AsyncSession, session_id: uuid.UUID, batch: EventBatch, *, user_id: uuid.UUID
) -> StudySession:
    """Merge a batch of events into the session's log and recompute it.

    Events may arrive late and out of order (an offline replay): the whole log
    is re-sorted and re-validated. An event already stored with the same details
    is skipped, so retries are safe. The batch is saved all or nothing.
    """
    study = await get_study_session(session, session_id, user_id=user_id, for_update=True)
    incoming = _dedupe_batch(batch.events)
    stored = {
        row.id: row
        for row in await session.scalars(
            select(SessionEvent).where(
                SessionEvent.user_id == user_id, SessionEvent.id.in_(incoming)
            )
        )
    }
    new: list[EventIn] = []
    for event in incoming.values():
        old = stored.get(event.id)
        if old is None:
            new.append(event)
        elif (old.session_id, old.type, old.occurred_at) != (
            study.id,
            event.type,
            event.occurred_at,
        ):
            raise Conflict(f"Event {event.id} was already recorded with different details")
    if not new:
        return study
    _check_not_future(event.occurred_at for event in new)

    log = [_as_event(row) for row in await events_of(session, study.id, user_id=user_id)]
    next_seq = max(event.seq for event in log) + 1
    # Provisional seqs keep the posted order; the database assigns larger ones in that order.
    log += [Event(e.type, e.occurred_at, next_seq + i) for i, e in enumerate(new)]
    timeline = replay(log)

    session.add_all(
        SessionEvent(
            user_id=user_id,
            id=event.id,
            session_id=study.id,
            type=event.type,
            occurred_at=event.occurred_at,
        )
        for event in new
    )
    _apply(study, timeline)
    await session.commit()
    return study


async def set_reflection(
    session: AsyncSession, session_id: uuid.UUID, data: ReflectionIn, *, user_id: uuid.UUID
) -> StudySession:
    """Save (or replace) the end-of-session reflection. Only for ended sessions."""
    study = await get_study_session(session, session_id, user_id=user_id)
    if study.state != "ended":
        raise Invalid("Reflect on a session once it has ended")
    for rating in data.topic_ratings:
        topic: Topic = await get_topic(session, rating.topic_id, user_id=user_id)
        if topic.module_id != study.module_id:
            raise Invalid("Rated topics must be in the session's module")

    await session.execute(
        delete(SessionTopicRating).where(SessionTopicRating.session_id == study.id)
    )
    session.add_all(
        SessionTopicRating(
            session_id=study.id,
            topic_id=rating.topic_id,
            module_id=study.module_id,
            confidence=rating.confidence,
        )
        for rating in data.topic_ratings
    )
    study.focus_rating = data.focus_rating
    study.covered_notes = data.covered_notes
    study.reflected_at = datetime.now(UTC)
    await session.commit()
    return study


async def delete_session(
    session: AsyncSession, session_id: uuid.UUID, *, user_id: uuid.UUID
) -> None:
    """Discard a session; its events and ratings go with it (FK cascades)."""
    study = await get_study_session(session, session_id, user_id=user_id)
    await session.delete(study)
    await session.commit()
