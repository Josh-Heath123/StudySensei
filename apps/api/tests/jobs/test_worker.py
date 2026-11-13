"""The job queue and worker: claim, succeed, retry with backoff, give up, reclaim."""

import hashlib
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.jobs import queue
from app.jobs.context import Handler, JobContext
from app.jobs.tasks import count_pages
from app.jobs.worker import GAVE_UP, HANDLERS, UNEXPECTED, SessionFactory, run_once
from app.models import Job, Material, User
from app.services.materials import COUNT_PAGES
from app.storage.base import blob_key
from app.storage.local import LocalStorage
from tests.academics.conftest import Rows
from tests.materials import samples

# The worker's clock in these tests: after any run_after the test transaction sets (its now()).
T0 = datetime.now(UTC) + timedelta(hours=1)


def at(moment: datetime) -> Callable[[], datetime]:
    return lambda: moment


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(tmp_path / "storage")


@pytest.fixture
def sessions(session: AsyncSession) -> SessionFactory:
    """The worker's session factory, handing out the rolled-back test session."""

    @asynccontextmanager
    async def factory() -> AsyncIterator[AsyncSession]:
        yield session

    return factory


async def a_material(
    session: AsyncSession, storage: LocalStorage, rows: Rows, data: bytes = samples.pdf(3)
) -> Material:
    """A stored PDF with its count_pages job queued, as the upload endpoint leaves it."""
    sha256 = hashlib.sha256(data).hexdigest()
    source = storage.root.parent / f"src-{uuid.uuid4().hex}"
    source.write_bytes(data)
    storage.put(blob_key(rows.user.id, sha256), source)
    material = Material(
        user_id=rows.user.id,
        module_id=rows.module.id,
        kind="slides",
        title="Week 3",
        original_filename="week3.pdf",
        content_type="application/pdf",
        size_bytes=len(data),
        sha256=sha256,
    )
    session.add(material)
    await session.flush()
    queue.enqueue(session, COUNT_PAGES, {"material_id": str(material.id)}, user_id=rows.user.id)
    await session.commit()
    return material


async def the_job(session: AsyncSession, user_id: uuid.UUID) -> Job:
    # populate_existing: the worker's rollbacks may have expired our copy.
    job = await session.scalar(
        select(Job).where(Job.user_id == user_id).execution_options(populate_existing=True)
    )
    assert job is not None
    return job


async def test_nothing_to_do(sessions: SessionFactory, storage: LocalStorage) -> None:
    assert await run_once(sessions, storage, now=lambda: T0) is False


async def test_a_job_runs_and_the_material_is_ready(
    session: AsyncSession, sessions: SessionFactory, storage: LocalStorage, alice: Rows
) -> None:
    user_id = alice.user.id  # the worker's rollbacks expire alice.user
    material = await a_material(session, storage, alice)

    assert await run_once(sessions, storage, now=lambda: T0) is True

    await session.refresh(material)
    assert (material.status, material.page_count, material.error) == ("ready", 3, None)
    job = await the_job(session, user_id)
    assert (job.status, job.attempts, job.locked_at, job.finished_at) == ("succeeded", 1, None, T0)
    assert await run_once(sessions, storage, now=lambda: T0) is False


async def test_a_failed_attempt_is_retried_with_backoff_then_succeeds(
    session: AsyncSession, sessions: SessionFactory, storage: LocalStorage, alice: Rows
) -> None:
    user_id = alice.user.id  # the worker's rollbacks expire alice.user
    material = await a_material(session, storage, alice)
    calls = 0

    async def flaky(ctx: JobContext) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ConnectionError("storage hiccup")
        await count_pages.run(ctx)

    handlers = {COUNT_PAGES: Handler(run=flaky, on_failure=count_pages.on_failure)}

    assert await run_once(sessions, storage, now=lambda: T0, handlers=handlers)

    job = await the_job(session, user_id)
    assert (job.status, job.attempts, job.locked_at) == ("queued", 1, None)
    assert job.run_after == T0 + timedelta(seconds=30)
    assert job.last_error == "ConnectionError: storage hiccup"
    await session.refresh(material)
    # Still processing, with a readable reason; the API shows it as retrying.
    assert (material.status, material.error) == ("processing", UNEXPECTED)

    # Not due yet.
    early = T0 + timedelta(seconds=29)
    assert not await run_once(sessions, storage, now=lambda: early, handlers=handlers)

    later = T0 + timedelta(seconds=30)
    assert await run_once(sessions, storage, now=lambda: later, handlers=handlers)

    job = await the_job(session, user_id)
    assert (job.status, job.attempts, job.last_error) == ("succeeded", 2, None)
    await session.refresh(material)
    assert (material.status, material.page_count, material.error) == ("ready", 3, None)


async def test_after_the_last_attempt_the_job_and_material_fail(
    session: AsyncSession, sessions: SessionFactory, storage: LocalStorage, alice: Rows
) -> None:
    user_id = alice.user.id  # the worker's rollbacks expire alice.user
    material = await a_material(session, storage, alice)

    async def broken(ctx: JobContext) -> None:
        raise RuntimeError("boom")

    handlers = {COUNT_PAGES: Handler(run=broken, on_failure=count_pages.on_failure)}
    now = T0
    for attempt in (1, 2, 3):
        assert await run_once(sessions, storage, now=at(now), handlers=handlers)
        job = await the_job(session, user_id)
        assert job.attempts == attempt
        now = job.run_after if job.status == "queued" else now

    assert [queue.backoff(n) for n in (1, 2, 3)] == [
        timedelta(seconds=30),
        timedelta(minutes=2),
        timedelta(minutes=8),
    ]
    assert queue.backoff(10) == timedelta(minutes=30)  # capped
    job = await the_job(session, user_id)
    assert (job.status, job.finished_at, job.last_error) == ("failed", now, "RuntimeError: boom")
    await session.refresh(material)
    assert (material.status, material.error) == ("failed", GAVE_UP)


async def test_an_expected_failure_shows_its_own_message(
    session: AsyncSession, sessions: SessionFactory, storage: LocalStorage, alice: Rows
) -> None:
    material = await a_material(session, storage, alice, data=b"%PDF-1.7 broken")

    await run_once(sessions, storage, now=lambda: T0)

    await session.refresh(material)
    assert material.status == "processing"
    assert material.error is not None and "damaged or password-protected" in material.error


async def test_a_missing_file_is_reported(
    session: AsyncSession, sessions: SessionFactory, storage: LocalStorage, alice: Rows
) -> None:
    material = await a_material(session, storage, alice)
    storage.delete(blob_key(alice.user.id, material.sha256))

    await run_once(sessions, storage, now=lambda: T0)

    await session.refresh(material)
    assert material.error == "The uploaded file is missing. Please upload it again."


async def test_a_job_for_a_deleted_material_just_succeeds(
    session: AsyncSession, sessions: SessionFactory, storage: LocalStorage, alice: Rows
) -> None:
    user_id = alice.user.id  # the worker's rollbacks expire alice.user
    material = await a_material(session, storage, alice)
    await session.execute(delete(Material).where(Material.id == material.id))
    await session.commit()

    assert await run_once(sessions, storage, now=lambda: T0)
    assert (await the_job(session, user_id)).status == "succeeded"


async def test_a_handler_never_touches_another_users_material(
    session: AsyncSession, sessions: SessionFactory, storage: LocalStorage, alice: Rows, bob: Rows
) -> None:
    hers = await a_material(session, storage, alice)
    # A job of Bob's that names Alice's material (it can't happen via the API; prove it's inert).
    queue.enqueue(session, COUNT_PAGES, {"material_id": str(hers.id)}, user_id=bob.user.id)
    await session.execute(delete(Job).where(Job.user_id == alice.user.id))
    await session.commit()

    assert await run_once(sessions, storage, now=lambda: T0)

    await session.refresh(hers)
    assert (hers.status, hers.page_count) == ("uploaded", None)


async def test_a_stale_running_job_is_reclaimed(
    session: AsyncSession, sessions: SessionFactory, storage: LocalStorage, alice: Rows
) -> None:
    await a_material(session, storage, alice)
    job = await queue.claim_next(session, T0)  # a worker took it, then died
    assert job is not None

    assert await queue.claim_next(session, T0 + timedelta(minutes=9)) is None
    reclaimed = await queue.claim_next(session, T0 + timedelta(minutes=11))

    assert reclaimed is not None and reclaimed.id == job.id
    assert reclaimed.attempts == 2


async def test_unknown_kinds_fail_without_crashing_the_worker(
    session: AsyncSession, sessions: SessionFactory, storage: LocalStorage, alice: Rows
) -> None:
    user_id = alice.user.id  # the worker's rollbacks expire alice.user
    queue.enqueue(session, "mystery", {}, user_id=alice.user.id, max_attempts=1)
    await session.commit()

    assert await run_once(sessions, storage, now=lambda: T0)

    job = await the_job(session, user_id)
    assert (job.status, job.last_error) == ("failed", "JobError: Unknown job kind 'mystery'")
    assert COUNT_PAGES in HANDLERS


async def test_two_workers_never_claim_the_same_job(engine: AsyncEngine) -> None:
    """SKIP LOCKED, on two real connections (committed rows, cleaned up after)."""
    async with AsyncSession(engine, expire_on_commit=False) as setup:
        user = User(email=f"worker-{uuid.uuid4().hex}@example.test", display_name="W")
        setup.add(user)
        await setup.flush()
        for _ in range(2):
            queue.enqueue(setup, "noop", {}, user_id=user.id)
        await setup.commit()
    try:
        async with (
            AsyncSession(engine, expire_on_commit=False) as first,
            AsyncSession(engine, expire_on_commit=False) as second,
        ):
            # Hold the first claim's lock open while the second worker looks.
            locked = await first.scalar(
                select(Job)
                .where(Job.user_id == user.id, Job.status == "queued")
                .order_by(Job.run_after, Job.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            other = await queue.claim_next(second, datetime.now(UTC) + timedelta(seconds=1))
            assert locked is not None and other is not None
            assert other.id != locked.id
            await first.rollback()
    finally:
        async with AsyncSession(engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == user.id))  # jobs cascade
            await cleanup.commit()
