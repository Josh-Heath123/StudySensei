"""A job that hits AIUnavailable waits for the providers instead of failing."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.errors import NOT_CONFIGURED, AIUnavailable
from app.ai.messages import user
from app.jobs import queue
from app.jobs.context import Handler, JobContext
from app.jobs.worker import run_once
from app.models import Job, User
from app.storage.local import LocalStorage
from tests.ai.conftest import MakeClient
from tests.fakes import FakeLLM, rate_limited

T0 = datetime.now(UTC) + timedelta(hours=1)


async def run(session: AsyncSession, tmp_path: Path, handler: Handler) -> None:
    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        yield session

    assert await run_once(
        sessions, LocalStorage(tmp_path / "s"), now=lambda: T0, handlers={"ai_test": handler}
    )


async def a_job(session: AsyncSession, user_a: User) -> Job:
    job = queue.enqueue(session, "ai_test", {}, user_id=user_a.id)
    await session.commit()
    return job


async def reload(session: AsyncSession, job: Job, tmp_path: Path, ask: Any, on_failure: Any) -> Job:
    """Run ``job`` through the worker, then read it back (the worker detaches it)."""
    job_id = job.id
    await run(session, tmp_path, Handler(run=ask, on_failure=on_failure))
    found = await session.get(Job, job_id, populate_existing=True)
    assert found is not None
    return found


async def test_rate_limited_job_is_rescheduled_without_using_an_attempt(
    session: AsyncSession,
    user_a: User,
    tmp_path: Path,
    make_client: MakeClient,
    fake_llm: FakeLLM,
) -> None:
    fake_llm.reply("flash", rate_limited(3600))
    fake_llm.reply("oss-120b", rate_limited(7200))
    client = make_client(now=T0)

    async def ask(ctx: JobContext) -> None:
        await client.complete_text(
            "smart", [user("Topics?")], purpose="topics", user_id=ctx.job.user_id
        )

    failures: list[str] = []

    async def on_failure(ctx: JobContext, message: str, *, retrying: bool) -> None:
        failures.append(message)

    job = await reload(session, await a_job(session, user_a), tmp_path, ask, on_failure)

    assert (job.status, job.attempts) == ("queued", 0)
    assert job.run_after == T0 + timedelta(hours=1)
    assert job.locked_at is None
    assert job.last_error is not None and job.last_error.startswith("AIUnavailable")
    assert failures == []  # the material isn't marked failed or retrying


async def test_no_provider_configured_fails_the_job_with_the_reason(
    session: AsyncSession, user_a: User, tmp_path: Path
) -> None:
    async def ask(ctx: JobContext) -> None:
        raise AIUnavailable(NOT_CONFIGURED, retry_at=None)

    failures: list[tuple[str, bool]] = []

    async def on_failure(ctx: JobContext, message: str, *, retrying: bool) -> None:
        failures.append((message, retrying))

    job = await reload(session, await a_job(session, user_a), tmp_path, ask, on_failure)

    assert job.status == "failed"
    assert failures == [(NOT_CONFIGURED, False)]
