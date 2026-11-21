"""Queueing push reminders (decision 0024): the window, who gets them, one per slot across
re-plans, a moved block reminded again, and the job sending to every device."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.kinds import PUSH_REMINDER
from app.jobs.worker import run_once
from app.models import AvailabilityException, Job, PlanBlock, PushSubscription, User
from app.services.planning.replan import move_block, replan
from app.services.push.reminders import queue_reminders
from app.services.push.sender import FakePushSender
from app.services.push.subscriptions import upsert
from app.storage.base import Storage
from tests.academics.conftest import Rows
from tests.planning.test_replan import NOW, blocks_of, setup
from tests.planning.test_replan_fixes import start_on

LEAD = timedelta(minutes=10)
SAST = ZoneInfo("Africa/Johannesburg")


async def subscribe(session: AsyncSession, user: User, name: str = "a") -> None:
    await upsert(
        session,
        user_id=user.id,
        endpoint=f"https://push.example/{name}",
        p256dh="BKey",
        auth="Auth",
        label=f"Edge on Windows ({name})",
    )


async def planned(session: AsyncSession, user: User) -> tuple[Rows, list[PlanBlock]]:
    """Evenings free, a test in 6 days; version 1 at NOW; one device subscribed."""
    rows = await setup(session, user)
    version = await replan(session, user_id=user.id, now=NOW, trigger="initial")
    await subscribe(session, user)
    return rows, await blocks_of(session, version)


async def reminder_jobs(session: AsyncSession, user: User) -> list[Job]:
    return list(
        await session.scalars(
            select(Job)
            .where(Job.user_id == user.id, Job.kind == PUSH_REMINDER)
            .order_by(Job.created_at)
        )
    )


async def test_the_window_is_after_now_up_to_the_lead_time(
    session: AsyncSession, user_a: User, push_on: FakePushSender
) -> None:
    _, blocks = await planned(session, user_a)
    first = blocks[0]

    assert await queue_reminders(session, first.start_at - LEAD - timedelta(seconds=1)) == 0
    assert await queue_reminders(session, first.start_at - LEAD) == 1  # exactly 10 min before
    [job] = await reminder_jobs(session, user_a)
    assert job.max_attempts == 1
    assert job.payload["payload"] == {
        "title": "Microservices at 18:00",
        "body": f"50 min · {first.method_text}",
        "url": "/",
        "tag": job.payload["slot_key"],
    }
    assert job.payload["start_at"] == first.start_at.isoformat()
    assert "ttl" not in job.payload  # worked out when sending
    # Once only, a minute later; and at its start it's no longer ahead.
    assert await queue_reminders(session, first.start_at - timedelta(minutes=9)) == 0
    assert await queue_reminders(session, first.start_at) == 0


async def test_the_lead_time_is_the_users(
    session: AsyncSession, user_a: User, push_on: FakePushSender
) -> None:
    _, blocks = await planned(session, user_a)
    user_a.reminder_minutes = 30
    await session.commit()
    assert await queue_reminders(session, blocks[0].start_at - timedelta(minutes=30)) == 1


async def test_without_vapid_keys_nothing_is_queued(
    session: AsyncSession, user_a: User, fake_push: FakePushSender
) -> None:
    _, blocks = await planned(session, user_a)
    at = blocks[0].start_at - timedelta(minutes=5)
    assert await queue_reminders(session, at) == 0  # no VAPID keys: push is disabled


async def test_reminders_off_or_no_devices(
    session: AsyncSession, user_a: User, push_on: FakePushSender
) -> None:
    _, blocks = await planned(session, user_a)
    at = blocks[0].start_at - timedelta(minutes=5)
    user_a.reminder_minutes = None
    await session.commit()
    assert await queue_reminders(session, at) == 0

    user_a.reminder_minutes = 10
    await session.execute(delete(PushSubscription).where(PushSubscription.user_id == user_a.id))
    await session.commit()
    assert await queue_reminders(session, at) == 0
    assert await reminder_jobs(session, user_a) == []


async def test_a_block_with_a_linked_session_isnt_reminded(
    session: AsyncSession, user_a: User, push_on: FakePushSender
) -> None:
    rows, blocks = await planned(session, user_a)
    await start_on(session, rows, blocks[0])  # started early from Next up
    assert await queue_reminders(session, blocks[0].start_at - timedelta(minutes=5)) == 0


async def test_only_the_users_own_blocks(
    session: AsyncSession, user_a: User, user_b: User, push_on: FakePushSender
) -> None:
    _, blocks = await planned(session, user_a)
    await subscribe(session, user_b, "bob")  # Bob has a device but no plan
    assert await queue_reminders(session, blocks[0].start_at - timedelta(minutes=5)) == 1
    assert await reminder_jobs(session, user_b) == []


async def test_one_reminder_per_slot_across_a_replan_with_fixed_copies(
    session: AsyncSession, user_a: User, push_on: FakePushSender
) -> None:
    _, blocks = await planned(session, user_a)
    first = blocks[0]
    at = first.start_at - timedelta(minutes=5)
    assert await queue_reminders(session, at) == 1

    # A change writes a new version; tonight's block is carried as a fixed copy, new id.
    session.add(
        AvailabilityException(
            user_id=user_a.id, date=(NOW + timedelta(days=2)).date(), unavailable=True, windows=[]
        )
    )
    await session.commit()
    second = await replan(session, user_id=user_a.id, now=at, trigger="availability")
    assert second.number == 2
    copy = next(b for b in await blocks_of(session, second) if b.start_at == first.start_at)
    assert copy.fixed and copy.id != first.id

    assert await queue_reminders(session, at + timedelta(minutes=1)) == 0
    assert len(await reminder_jobs(session, user_a)) == 1


async def test_a_moved_block_is_a_new_slot_and_reminded_again(
    session: AsyncSession, user_a: User, push_on: FakePushSender
) -> None:
    _, blocks = await planned(session, user_a)
    later = blocks[1]
    # Reminded at its old time (we're 5 minutes before it)...
    at = later.start_at - timedelta(minutes=5)
    assert await queue_reminders(session, at) >= 1
    # ...then moved to 20:00 SAST the next evening, clear of that evening's blocks.
    local = later.start_at.astimezone(SAST) + timedelta(days=1)
    target = local.replace(hour=20, minute=0).astimezone(UTC)
    length = later.end_at - later.start_at
    clear = [
        b
        for b in blocks
        if b.id != later.id
        and b.start_at < target + length + timedelta(minutes=10)
        and b.end_at > target - timedelta(minutes=10)
    ]
    assert clear == [], "the scenario needs a clear 20:00 the next evening"
    moved = await move_block(session, later.id, target, user_id=user_a.id, now=at)
    copy = next(b for b in await blocks_of(session, moved) if b.start_at == target)
    assert copy.pinned

    before = len(await reminder_jobs(session, user_a))
    assert await queue_reminders(session, target - timedelta(minutes=5)) >= 1
    jobs = await reminder_jobs(session, user_a)
    assert len(jobs) > before
    assert jobs[-1].payload["payload"]["title"].endswith("at 20:00")


async def test_the_job_sends_to_every_device(
    session: AsyncSession, user_a: User, push_on: FakePushSender
) -> None:
    _, blocks = await planned(session, user_a)
    await subscribe(session, user_a, "b")
    first = blocks[0]
    await queue_reminders(session, first.start_at - timedelta(minutes=5))

    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        yield session

    storage: Storage = None  # type: ignore[assignment]  # a reminder never touches files
    assert await run_once(sessions, storage, now=lambda: first.start_at - timedelta(minutes=5))
    assert sorted(target.endpoint for target, _, _ in push_on.sent) == [
        "https://push.example/a",
        "https://push.example/b",
    ]
    assert {payload["title"] for _, payload, _ in push_on.sent} == {"Microservices at 18:00"}
    [job] = await reminder_jobs(session, user_a)
    await session.refresh(job)
    assert job.status == "succeeded"


async def run_reminder_at(session: AsyncSession, at: datetime) -> bool:
    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        yield session

    storage: Storage = None  # type: ignore[assignment]  # a reminder never touches files
    return await run_once(sessions, storage, now=lambda: at)


async def test_the_ttl_is_worked_out_when_sending(
    session: AsyncSession, user_a: User, push_on: FakePushSender
) -> None:
    """Post-merge review of #47: queued 10 minutes ahead but sent 4 minutes before the block,
    the reminder lives 4 minutes, not 10."""
    _, blocks = await planned(session, user_a)
    first = blocks[0]
    await queue_reminders(session, first.start_at - LEAD)
    assert await run_reminder_at(session, first.start_at - timedelta(minutes=4))
    assert [ttl for _, _, ttl in push_on.sent] == [240]


async def test_a_reminder_for_a_started_block_is_dropped_without_sending(
    session: AsyncSession, user_a: User, push_on: FakePushSender
) -> None:
    _, blocks = await planned(session, user_a)
    first = blocks[0]
    await queue_reminders(session, first.start_at - LEAD)
    assert await run_reminder_at(session, first.start_at + timedelta(seconds=1))
    assert push_on.sent == []
    [job] = await reminder_jobs(session, user_a)
    await session.refresh(job)
    assert job.status == "succeeded"  # dropped, not failed: nothing to retry
