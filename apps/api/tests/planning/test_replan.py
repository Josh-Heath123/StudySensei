"""Re-planning and stored plans (decision 0021), against real Postgres: versions, skip, finish,
missed blocks, coalescing, the lock, no churn, today's minutes and the nightly queue."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.jobs.queue import enqueue_replan
from app.models import (
    AvailabilityRule,
    Job,
    PlanBlock,
    PlanVersion,
    StudySession,
    User,
)
from app.schemas.academics import AssessmentUpdate
from app.schemas.sessions import EventBatch, SessionStart
from app.services.academics import assessments
from app.services.planning.inputs import load_plan_data
from app.services.planning.planner import required_minutes
from app.services.planning.replan import (
    current_version,
    last_nightly,
    queue_nightly_replans,
    replan,
    skip_block,
)
from app.services.sessions import sessions
from tests.academics.conftest import Rows, forget_replans, make_rows

SAST = ZoneInfo("Africa/Johannesburg")
# Monday 1 March 2027, 08:00 in Johannesburg: after any real run of these tests, so the
# fixtures' real-time sessions are never "today".
NOW = datetime(2027, 3, 1, 8, 0, tzinfo=SAST)


async def evenings(session: AsyncSession, user: User) -> None:
    for weekday in range(7):
        session.add(
            AvailabilityRule(user_id=user.id, weekday=weekday, start_minute=1080, end_minute=1260)
        )
    await session.commit()


async def setup(session: AsyncSession, user: User, workload: int = 300) -> Rows:
    """Evenings 18:00-21:00 every day; a test in 6 days on one topic of ``workload`` minutes."""
    rows = await make_rows(session, user)
    await evenings(session, user)
    rows.assessment.due_at = NOW + timedelta(days=6)
    rows.topic.estimated_minutes = workload
    await session.commit()
    await forget_replans(session, user)
    return rows


async def blocks_of(session: AsyncSession, version: PlanVersion) -> list[PlanBlock]:
    return list(
        await session.scalars(
            select(PlanBlock).where(PlanBlock.version_id == version.id).order_by(PlanBlock.start_at)
        )
    )


async def queued_replans(session: AsyncSession, user: User) -> list[Job]:
    return list(
        await session.scalars(
            select(Job).where(Job.user_id == user.id, Job.kind == "replan", Job.status == "queued")
        )
    )


# --- the scenario ----------------------------------------------------------------------


async def test_first_version_then_a_skip(session: AsyncSession, user_a: User) -> None:
    rows = await setup(session, user_a)

    first = await replan(session, user_id=user_a.id, now=NOW, trigger="initial")

    assert (first.number, first.trigger, first.summary) == (1, "initial", "Your first plan.")
    assert first.checked_at == first.generated_at == NOW
    assert first.report["overall"]["line"].startswith("You need ")
    v1 = await blocks_of(session, first)
    assert v1 and all(b.status == "planned" and not b.fixed for b in v1)
    assert all(b.reason_text and b.method_text for b in v1)

    skipped = v1[0]
    second = await skip_block(session, skipped.id, user_id=user_a.id, now=NOW)

    assert (second.number, second.trigger) == (2, "skip")
    assert (
        second.summary == "You skipped Microservices (Mon 1 Mar, 18:00): its time is placed again."
    )
    await session.refresh(skipped)
    assert (skipped.status, skipped.status_changed_at) == ("skipped", NOW)
    assert skipped.version_id == first.id  # it stays on its own version
    v2 = await blocks_of(session, second)
    soon = [b for b in v1 if b.start_at < NOW + timedelta(hours=24) and b.id != skipped.id]
    # The next 24 h are kept, except the skipped block, with the texts they had.
    assert [(b.start_at, b.reason_text) for b in v2 if b.fixed] == [
        (b.start_at, b.reason_text) for b in soon
    ]
    assert all(b.start_at != skipped.start_at for b in v2)

    # Its time is placed again: the topic still gets every minute it needs.
    def study(blocks: list[PlanBlock]) -> int:
        return sum(int((b.end_at - b.start_at).total_seconds() // 60) for b in blocks if b.topic_id)

    assert study(v2) == study(v1)
    assert (await current_version(session, user_id=user_a.id)) == second
    del rows


async def test_a_linked_session_finishes_its_block(session: AsyncSession, user_a: User) -> None:
    rows = await setup(session, user_a)
    version = await replan(session, user_id=user_a.id, now=NOW, trigger="initial")
    block = (await blocks_of(session, version))[0]
    before = await load_plan_data(session, user_id=user_a.id, now=NOW)

    # Events are real times in the past (the API refuses future ones); the block is the link.
    started = datetime.now(UTC) - timedelta(hours=2)
    study, _ = await sessions.start_session(
        session,
        SessionStart.model_validate(
            {
                "module_id": rows.module.id,
                "topic_id": rows.topic.id,
                "plan_block_id": block.id,
                "start": {"id": uuid.uuid4(), "occurred_at": started},
            }
        ),
        user_id=user_a.id,
    )
    end = {"id": uuid.uuid4(), "type": "end", "occurred_at": started + timedelta(minutes=50)}
    await sessions.add_events(
        session, study.id, EventBatch.model_validate({"events": [end]}), user_id=user_a.id
    )

    await session.refresh(block)
    assert (block.status, block.status_changed_at) == ("done", started + timedelta(minutes=50))
    [job] = await queued_replans(session, user_a)
    assert job.payload == {
        "trigger": "finish",
        "detail": {"block_id": str(block.id), "minutes": 50},
    }
    # The unit's required minutes fall by the measured 50.
    after = await load_plan_data(session, user_id=user_a.id, now=NOW)
    topic = next(t for t in after.input.topics if t.id == rows.topic.id)
    was = before.input.studied_minutes.get(rows.topic.id, 0)
    assert after.input.studied_minutes[rows.topic.id] == was + 50
    assert required_minutes(topic, was) - required_minutes(topic, was + 50) == 50

    # Replaying the end again changes nothing, and queues nothing more.
    await forget_replans(session, user_a)
    await sessions.add_events(
        session, study.id, EventBatch.model_validate({"events": [end]}), user_id=user_a.id
    )
    assert await queued_replans(session, user_a) == []

    # The re-plan it queued names the block and the measured time.
    finished = await replan(
        session, user_id=user_a.id, now=NOW, trigger="finish", detail=job.payload["detail"]
    )
    assert finished.summary == "You finished a block on Microservices (measured 50 min)."


async def test_the_nightly_run_marks_unattended_blocks_missed(
    session: AsyncSession, user_a: User
) -> None:
    await setup(session, user_a)
    version = await replan(session, user_id=user_a.id, now=NOW, trigger="initial")
    first_evening = [
        b for b in await blocks_of(session, version) if b.start_at < NOW + timedelta(hours=24)
    ]
    assert first_evening

    night = NOW.replace(hour=3, minute=10) + timedelta(days=1)  # Tuesday 03:10
    assert await queue_nightly_replans(session, night) == 1
    [job] = await queued_replans(session, user_a)
    assert job.payload["trigger"] == "nightly"
    nightly = await replan(session, user_id=user_a.id, now=night, trigger="nightly")

    for block in first_evening:
        await session.refresh(block)
        assert (block.status, block.status_changed_at) == ("missed", night)
    assert nightly.number == 2
    assert nightly.summary == "Updated overnight."


# --- coalescing, the lock, no churn ----------------------------------------------------


async def test_two_triggers_in_a_row_leave_one_queued_replan(
    session: AsyncSession, user_a: User
) -> None:
    rows = await setup(session, user_a)
    for title in ("Test 1", "Test 1 (moved)"):
        await assessments.update_assessment(
            session, rows.assessment.id, AssessmentUpdate(title=title), user_id=user_a.id
        )
    await enqueue_replan(session, user_id=user_a.id, trigger="availability")
    await session.commit()

    [job] = await queued_replans(session, user_a)
    # The first trigger is kept.
    assert job.payload == {
        "trigger": "assessment",
        "detail": {"assessment_id": str(rows.assessment.id), "name": "COS330 Test 1"},
    }
    # A running re-plan doesn't absorb the next change: it queues another.
    job.status, job.locked_at = "running", NOW
    await session.commit()
    await enqueue_replan(session, user_id=user_a.id, trigger="availability")
    await session.commit()
    assert len(await queued_replans(session, user_a)) == 1


async def test_a_replan_with_no_change_writes_no_version(
    session: AsyncSession, user_a: User
) -> None:
    await setup(session, user_a)
    first = await replan(session, user_id=user_a.id, now=NOW, trigger="initial")
    later = NOW + timedelta(minutes=5)

    again = await replan(session, user_id=user_a.id, now=later, trigger="manual")

    assert again.id == first.id
    assert (again.number, again.trigger, again.generated_at, again.checked_at) == (
        1,
        "initial",
        NOW,
        later,
    )
    count = await session.scalar(
        select(func.count()).select_from(PlanVersion).where(PlanVersion.user_id == user_a.id)
    )
    assert count == 1


async def test_concurrent_replans_are_serialised(engine: AsyncEngine) -> None:
    """Real commits on separate connections: without the lock, two runs would both write
    version 1 (or the same next number)."""
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as setup_session:
        user = User(email=f"lock-{uuid.uuid4()}@example.test", display_name="Lock")
        setup_session.add(user)
        await setup_session.commit()
        await setup(setup_session, user)
    try:
        # Different clocks give different plans, so every run that gets the lock writes.
        nows = [NOW + timedelta(hours=hours) for hours in (0, 30, 54, 78)]

        async def run(now: datetime) -> int:
            async with maker() as own:
                return (await replan(own, user_id=user.id, now=now, trigger="manual")).number

        numbers = await asyncio.gather(*(run(now) for now in nows))
        async with maker() as check:
            stored = list(
                await check.scalars(
                    select(PlanVersion.number)
                    .where(PlanVersion.user_id == user.id)
                    .order_by(PlanVersion.number)
                )
            )
        assert stored == list(range(1, len(stored) + 1))
        assert sorted(set(numbers)) == stored
    finally:
        async with maker() as cleanup:
            await cleanup.execute(delete(User).where(User.id == user.id))
            await cleanup.commit()


# --- today's minutes and the nightly queue ---------------------------------------------


async def test_minutes_studied_today_reduce_todays_cap(session: AsyncSession, user_a: User) -> None:
    rows = await setup(session, user_a, workload=900)
    user_a.daily_study_cap_minutes = 120
    session.add(
        StudySession(
            user_id=user_a.id,
            module_id=rows.module.id,
            topic_id=rows.topic.id,
            state="ended",
            started_at=NOW.replace(hour=6),
            ended_at=NOW.replace(hour=7, minute=20),
            last_event_at=NOW.replace(hour=7, minute=20),
            active_seconds=80 * 60,
            break_seconds=0,
        )
    )
    await session.commit()

    data = await load_plan_data(session, user_id=user_a.id, now=NOW)
    assert data.input.studied_on == {NOW.date(): 80}
    version = await replan(session, user_id=user_a.id, now=NOW, trigger="initial")
    today = [
        b
        for b in await blocks_of(session, version)
        if b.start_at.astimezone(SAST).date() == NOW.date()
    ]
    # 80 of 120 minutes are used: no 50-minute block fits today.
    assert today == []


def test_the_most_recent_local_3am() -> None:
    assert last_nightly(NOW, SAST) == NOW.replace(hour=3)
    assert last_nightly(NOW.replace(hour=2), SAST) == NOW.replace(hour=3) - timedelta(days=1)


async def test_nightly_replans_are_queued_once_per_user_per_local_night(
    session: AsyncSession, user_a: User, user_b: User
) -> None:
    await setup(session, user_a)
    await replan(session, user_id=user_a.id, now=NOW, trigger="initial")
    # Bob has no plan: skipped.
    night = NOW.replace(hour=3, minute=30) + timedelta(days=1)

    assert await queue_nightly_replans(session, night) == 1
    assert await queue_nightly_replans(session, night + timedelta(minutes=1)) == 0
    # The job runs (checked_at moves past 03:00): nothing more that night.
    [job] = await queued_replans(session, user_a)
    job.status = "succeeded"
    await replan(session, user_id=user_a.id, now=night, trigger="nightly")
    assert await queue_nightly_replans(session, night + timedelta(hours=20)) == 0
    # The next night, once more.
    assert await queue_nightly_replans(session, night + timedelta(days=1)) == 1
    assert await queued_replans(session, user_b) == []
