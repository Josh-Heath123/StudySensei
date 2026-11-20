"""Reading the stored plan (decision 0022): history across versions, the derived missed status
(no write), each block's actions, the linked session's measured minutes, and replan_pending."""

from datetime import timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.queue import enqueue_replan
from app.models import User
from app.services.planning.replan import replan, skip_block
from app.services.planning.stored import next_block, plan_for
from tests.planning.test_replan import NOW, blocks_of, setup
from tests.planning.test_replan_fixes import end, start_on


async def test_history_holds_skipped_blocks_but_never_superseded_ones(
    session: AsyncSession, user_a: User
) -> None:
    await setup(session, user_a)
    first = await replan(session, user_id=user_a.id, now=NOW, trigger="initial")
    v1 = await blocks_of(session, first)
    second = await skip_block(session, v1[0].id, user_id=user_a.id, now=NOW)

    shown = await plan_for(session, user_id=user_a.id, now=NOW)

    assert shown.number == second.number
    ids = {b.id for b in shown.blocks}
    v2 = {b.id for b in await blocks_of(session, second)}
    # The current version's blocks in range, plus the skipped one from version 1 ...
    assert v1[0].id in ids
    assert ids - {v1[0].id} <= v2
    # ... and none of version 1's superseded planned rows.
    assert not ids & {b.id for b in v1[1:]}
    skipped = next(b for b in shown.blocks if b.id == v1[0].id)
    assert (skipped.status, skipped.actions.skip, skipped.actions.start) == (
        "skipped",
        False,
        False,
    )


async def test_an_unattended_past_block_reads_as_missed_without_a_write(
    session: AsyncSession, user_a: User
) -> None:
    await setup(session, user_a)
    first = await replan(session, user_id=user_a.id, now=NOW, trigger="initial")
    tonight = (await blocks_of(session, first))[0]
    later = tonight.end_at + timedelta(minutes=5)

    shown = await plan_for(session, user_id=user_a.id, now=later)

    block = next(b for b in shown.blocks if b.id == tonight.id)
    assert block.status == "missed"
    assert block.actions.model_dump() == {"start": False, "skip": False, "move": False}
    await session.refresh(tonight)
    assert tonight.status == "planned"


async def test_actions_follow_the_block_and_the_sessions(
    session: AsyncSession, user_a: User
) -> None:
    rows = await setup(session, user_a)
    first = await replan(session, user_id=user_a.id, now=NOW, trigger="initial")
    tonight, later = (await blocks_of(session, first))[:2]

    upcoming = await next_block(session, user_id=user_a.id, now=NOW)
    assert upcoming is not None and upcoming.id == tonight.id
    assert upcoming.actions.model_dump() == {"start": True, "skip": True, "move": True}
    # Started (its time has come): it can't be moved, but can still be started or skipped.
    during = await next_block(
        session, user_id=user_a.id, now=tonight.start_at + timedelta(minutes=5)
    )
    assert during is not None
    assert during.actions.model_dump() == {"start": True, "skip": True, "move": False}

    study = await start_on(session, rows, tonight)
    shown = {b.id: b for b in (await plan_for(session, user_id=user_a.id, now=NOW)).blocks}
    # Its open session: no skip, no move, and no other start while it's open.
    assert shown[tonight.id].actions.model_dump() == {"start": False, "skip": False, "move": False}
    assert shown[tonight.id].linked_session_id == study.id
    assert shown[later.id].actions.model_dump() == {"start": False, "skip": True, "move": True}

    await end(session, rows, study)
    shown = {b.id: b for b in (await plan_for(session, user_id=user_a.id, now=NOW)).blocks}
    # Done, it's shown on the day it was studied (decision 0023), not in its planned slot.
    assert tonight.id not in shown
    assert shown[later.id].actions.start is True
    await session.refresh(study)
    day = study.started_at.astimezone(ZoneInfo("Africa/Johannesburg")).date()
    studied = await plan_for(session, user_id=user_a.id, now=NOW, first=day, last=day)
    done = next(b for b in studied.blocks if b.id == tonight.id)
    assert (done.status, done.session_minutes) == ("done", 48)
    assert (done.start, done.end) == (study.started_at, study.ended_at)
    assert (done.planned_start, done.planned_end) == (tonight.start_at, tonight.end_at)


async def test_replan_pending(session: AsyncSession, user_a: User) -> None:
    await setup(session, user_a)
    await replan(session, user_id=user_a.id, now=NOW, trigger="initial")
    assert (await plan_for(session, user_id=user_a.id, now=NOW)).replan_pending is False
    await enqueue_replan(session, user_id=user_a.id, trigger="availability")
    await session.commit()
    assert (await plan_for(session, user_id=user_a.id, now=NOW)).replan_pending is True
