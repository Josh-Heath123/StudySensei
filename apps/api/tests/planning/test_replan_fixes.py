"""Fixes from the review of #45 (decision 0022): a linked session follows its block across
re-plans, a true skip summary, version 1's summary, and no nightly retry loop."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AvailabilityException, AvailabilityRule, Job, PlanBlock, StudySession, User
from app.schemas.sessions import EventBatch, SessionStart
from app.services.errors import Conflict
from app.services.planning import stored
from app.services.planning.replan import (
    current_version,
    queue_nightly_replans,
    replan,
    skip_block,
)
from app.services.sessions import sessions
from tests.academics.conftest import Rows, forget_replans
from tests.planning.test_replan import NOW, blocks_of, setup


async def start_on(session: AsyncSession, rows: Rows, block: PlanBlock) -> StudySession:
    """A session for ``block``, started two hours ago in real time (the API refuses future
    events; the block is the link, not the time)."""
    study, _ = await sessions.start_session(
        session,
        SessionStart.model_validate(
            {
                "module_id": rows.module.id,
                "topic_id": block.topic_id,
                "plan_block_id": block.id,
                "start": {
                    "id": uuid.uuid4(),
                    "occurred_at": datetime.now(UTC) - timedelta(hours=2),
                },
            }
        ),
        user_id=rows.user.id,
    )
    return study


async def end(session: AsyncSession, rows: Rows, study: StudySession) -> None:
    event = {
        "id": uuid.uuid4(),
        "type": "end",
        "occurred_at": study.started_at + timedelta(minutes=48),
    }
    await sessions.add_events(
        session, study.id, EventBatch.model_validate({"events": [event]}), user_id=rows.user.id
    )


# --- a. a linked session follows its block -----------------------------------------------


async def test_a_linked_session_follows_its_block_into_a_new_version(
    session: AsyncSession, user_a: User
) -> None:
    rows = await setup(session, user_a)
    first = await replan(session, user_id=user_a.id, now=NOW, trigger="initial")
    block = (await blocks_of(session, first))[0]
    study = await start_on(session, rows, block)

    # A change that writes a new version: Wednesday off. Tonight's block is kept as a copy.
    session.add(
        AvailabilityException(
            user_id=user_a.id, date=(NOW + timedelta(days=2)).date(), unavailable=True, windows=[]
        )
    )
    await session.commit()
    second = await replan(session, user_id=user_a.id, now=NOW, trigger="availability")
    assert second.number == 2
    copy = next(b for b in await blocks_of(session, second) if b.start_at == block.start_at)
    assert copy.fixed and copy.id != block.id
    await session.refresh(study)
    assert study.plan_block_id == copy.id

    await end(session, rows, study)

    await session.refresh(copy)
    assert copy.status == "done"
    # After the block's time, a re-plan marks nothing missed, and the next block moves on.
    later = copy.end_at + timedelta(minutes=10)
    await replan(session, user_id=user_a.id, now=later, trigger="manual")
    await session.refresh(copy)
    assert copy.status == "done"
    upcoming = await stored.next_block(session, user_id=user_a.id, now=NOW)
    assert upcoming is not None and upcoming.start != block.start_at


async def test_finishing_marks_only_a_planned_block_done(
    session: AsyncSession, user_a: User
) -> None:
    rows = await setup(session, user_a)
    first = await replan(session, user_id=user_a.id, now=NOW, trigger="initial")
    block = (await blocks_of(session, first))[0]
    study = await start_on(session, rows, block)
    # Meanwhile the block was marked skipped some other way (an old client, say).
    block.status = "skipped"
    await session.commit()

    await end(session, rows, study)

    await session.refresh(block)
    assert block.status == "skipped"


async def test_a_block_with_an_open_session_cant_be_skipped(
    session: AsyncSession, user_a: User
) -> None:
    rows = await setup(session, user_a)
    first = await replan(session, user_id=user_a.id, now=NOW, trigger="initial")
    block = (await blocks_of(session, first))[0]
    await start_on(session, rows, block)

    with pytest.raises(Conflict, match=r"Its session is still open."):
        await skip_block(session, block.id, user_id=user_a.id, now=NOW)


# --- b. the skip summary is true -------------------------------------------------------


async def test_a_skip_with_no_room_left_says_the_assessment_is_now_shorter(
    session: AsyncSession, user_a: User
) -> None:
    # One hour each evening and far more work than fits: every free minute is used.
    rows = await setup(session, user_a, workload=1500)
    await session.execute(
        update(AvailabilityRule)
        .where(AvailabilityRule.user_id == user_a.id)
        .values(end_minute=1140)
    )
    await session.commit()
    first = await replan(session, user_id=user_a.id, now=NOW, trigger="initial")
    block = (await blocks_of(session, first))[0]

    second = await skip_block(session, block.id, user_id=user_a.id, now=NOW)

    def short(report: dict[str, object]) -> int:
        entries = report["assessments"]
        assert isinstance(entries, list)
        return int(
            next(
                a["short_minutes"] for a in entries if a["assessment_id"] == str(rows.assessment.id)
            )
        )

    assert short(second.report) > short(first.report)
    hours, minutes = divmod(short(second.report), 60)
    shown = f"{hours} h" if minutes == 0 else f"{hours} h {minutes:02d}"
    assert second.summary == (
        "You skipped Microservices (Mon 1 Mar, 18:00). There's no free time left to place it "
        f"again before COS330 Semester test 1, which is now {shown} short."
    )


async def test_a_skip_with_room_left_says_its_time_is_placed_again(
    session: AsyncSession, user_a: User
) -> None:
    await setup(session, user_a)
    first = await replan(session, user_id=user_a.id, now=NOW, trigger="initial")
    block = (await blocks_of(session, first))[0]

    second = await skip_block(session, block.id, user_id=user_a.id, now=NOW)

    assert second.summary == (
        "You skipped Microservices (Mon 1 Mar, 18:00): its time is placed again."
    )


# --- c. version 1 ----------------------------------------------------------------------


async def test_version_1_is_always_your_first_plan(session: AsyncSession, user_a: User) -> None:
    await setup(session, user_a)
    first = await replan(session, user_id=user_a.id, now=NOW, trigger="availability")
    assert (first.number, first.trigger, first.summary) == (
        1,
        "availability",
        "Your first plan.",
    )


# --- d. no nightly retry loop ----------------------------------------------------------


@pytest.mark.parametrize(("failed_hours_after_3am", "queued"), [(1, 0), (-1, 1)])
async def test_a_replan_that_failed_tonight_isnt_queued_again(
    session: AsyncSession, user_a: User, failed_hours_after_3am: int, queued: int
) -> None:
    await setup(session, user_a)
    await replan(session, user_id=user_a.id, now=NOW, trigger="initial")
    three = (NOW + timedelta(days=1)).replace(hour=3, minute=0)
    session.add(
        Job(
            user_id=user_a.id,
            kind="replan",
            payload={"trigger": "nightly", "detail": {}},
            status="failed",
            attempts=3,
            finished_at=three + timedelta(hours=failed_hours_after_3am),
            last_error="RuntimeError: boom",
        )
    )
    await session.commit()

    assert await queue_nightly_replans(session, three + timedelta(hours=2)) == queued
    await forget_replans(session, user_a)
    assert await current_version(session, user_id=user_a.id) is not None
