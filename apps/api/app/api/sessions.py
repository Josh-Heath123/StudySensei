import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from pydantic import AwareDatetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.core.db import SessionDep
from app.models import StudySession
from app.schemas.sessions import (
    EventBatch,
    EventOut,
    ModuleSessionSummary,
    ReflectionIn,
    SessionDetailOut,
    SessionFields,
    SessionOut,
    SessionPage,
    SessionStart,
    TopicRatingOut,
)
from app.services.sessions import sessions

router = APIRouter(tags=["sessions"])


async def _out(
    session: AsyncSession, items: list[StudySession], *, user_id: uuid.UUID
) -> list[SessionOut]:
    ratings = await sessions.ratings_for(session, [s.id for s in items], user_id=user_id)
    return [
        SessionOut(
            **SessionFields.model_validate(s).model_dump(),
            topic_ratings=[TopicRatingOut.model_validate(r) for r in ratings[s.id]],
        )
        for s in items
    ]


async def _detail(
    session: AsyncSession, item: StudySession, *, user_id: uuid.UUID
) -> SessionDetailOut:
    (out,) = await _out(session, [item], user_id=user_id)
    events = await sessions.events_of(session, item.id, user_id=user_id)
    return SessionDetailOut(**out.model_dump(), events=[EventOut.model_validate(e) for e in events])


@router.post("/sessions", response_model=SessionDetailOut, status_code=status.HTTP_201_CREATED)
async def start_session(
    data: SessionStart, response: Response, session: SessionDep, user: CurrentUser
) -> SessionDetailOut:
    """Open a session with its start event (201).

    Resending the same start event returns the existing session (200). Only one
    session can be open at a time (409).
    """
    item, created = await sessions.start_session(session, data, user_id=user.id)
    if not created:
        response.status_code = status.HTTP_200_OK
    return await _detail(session, item, user_id=user.id)


@router.get("/sessions/active", response_model=SessionDetailOut | None)
async def get_active_session(session: SessionDep, user: CurrentUser) -> SessionDetailOut | None:
    """Your open session with its events (to resume the timer after a reload), or null."""
    item = await sessions.get_active_session(session, user_id=user.id)
    return None if item is None else await _detail(session, item, user_id=user.id)


@router.get("/sessions/{session_id}", response_model=SessionDetailOut)
async def get_session(
    session_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> SessionDetailOut:
    item = await sessions.get_study_session(session, session_id, user_id=user.id)
    return await _detail(session, item, user_id=user.id)


@router.post("/sessions/{session_id}/events", response_model=SessionDetailOut)
async def add_events(
    session_id: uuid.UUID, data: EventBatch, session: SessionDep, user: CurrentUser
) -> SessionDetailOut:
    """Add timer events, in any order. Already-stored ids are skipped if unchanged (409 if not).

    The whole log is replayed: an impossible sequence (e.g. resume while active) is a
    422 and nothing in the batch is saved.
    """
    item = await sessions.add_events(session, session_id, data, user_id=user.id)
    return await _detail(session, item, user_id=user.id)


@router.put("/sessions/{session_id}/reflection", response_model=SessionOut)
async def set_reflection(
    session_id: uuid.UUID, data: ReflectionIn, session: SessionDep, user: CurrentUser
) -> SessionOut:
    """Save the end-of-session reflection, replacing any earlier one (ended sessions only)."""
    item = await sessions.set_reflection(session, session_id, data, user_id=user.id)
    (out,) = await _out(session, [item], user_id=user.id)
    return out


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> None:
    await sessions.delete_session(session, session_id, user_id=user.id)


@router.get("/modules/{module_id}/sessions", response_model=SessionPage)
async def list_module_sessions(
    module_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SessionPage:
    """A page of the module's sessions: the open one first, then newest first."""
    items, total = await sessions.list_module_sessions(
        session, module_id, user_id=user.id, limit=limit, offset=offset
    )
    out = await _out(session, items, user_id=user.id)
    return SessionPage(items=out, total=total, limit=limit, offset=offset)


@router.get("/modules/{module_id}/sessions/summary", response_model=ModuleSessionSummary)
async def module_session_summary(
    module_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
    week_start: Annotated[AwareDatetime, Query()],
) -> ModuleSessionSummary:
    """Measured study time for the module: all time, and since `week_start` (your local week)."""
    totals = await sessions.module_session_totals(
        session, module_id, user_id=user.id, week_start=week_start
    )
    return ModuleSessionSummary(
        session_count=totals.session_count,
        active_seconds=totals.active_seconds,
        week_start=week_start,
        week_active_seconds=totals.week_active_seconds,
    )
