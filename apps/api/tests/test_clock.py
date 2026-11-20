"""The clock and FAKE_NOW (decision 0023): honoured on the demo and e2e databases only, and
queued jobs run on the clock's time, not Postgres's."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.config import Settings, database_name
from app.jobs import queue
from app.models import User

DEMO = "postgresql+asyncpg://studysensei:studysensei@localhost:5433/studysensei_demo"
FAKE = "2026-11-16T10:40:00+02:00"


def test_database_name() -> None:
    assert database_name(DEMO) == "studysensei_demo"
    assert database_name("postgresql+asyncpg://u:p@h:1/studysensei_e2e?ssl=off") == (
        "studysensei_e2e"
    )


@pytest.mark.parametrize("db", ["studysensei_demo", "studysensei_e2e"])
def test_fake_now_on_the_demo_and_e2e_databases(
    monkeypatch: pytest.MonkeyPatch, db: str
) -> None:
    settings = Settings(database_url=DEMO.replace("studysensei_demo", db), fake_now=FAKE)
    monkeypatch.setattr(clock, "get_settings", lambda: settings)
    assert clock.now() == datetime(2026, 11, 16, 8, 40, tzinfo=UTC)
    assert clock.now().tzinfo == UTC


@pytest.mark.parametrize("db", ["studysensei", "studysensei_test", "demo_studysensei"])
def test_fake_now_elsewhere_fails_with_a_clear_error(db: str) -> None:
    with pytest.raises(ValidationError, match=f"FAKE_NOW is set, but the database is '{db}'"):
        Settings(database_url=DEMO.replace("studysensei_demo", db), fake_now=FAKE)


def test_fake_now_needs_a_timezone() -> None:
    with pytest.raises(ValidationError):
        Settings(database_url=DEMO, fake_now="2026-11-16T10:40:00")


def test_blank_fake_now_is_the_real_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(database_url="postgresql+asyncpg://u:p@h:1/studysensei", fake_now="")
    monkeypatch.setattr(clock, "get_settings", lambda: settings)
    assert abs(clock.now() - datetime.now(UTC)) < timedelta(seconds=5)


async def test_a_job_queued_on_a_fake_clock_runs_on_it(
    session: AsyncSession, user_a: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Days in the past, as the demo's "now" is: Postgres's now() would be in its future.
    settings = Settings(database_url=DEMO, fake_now="2026-01-05T09:00:00+00:00")
    monkeypatch.setattr(clock, "get_settings", lambda: settings)
    queue.enqueue(session, "replan", {"trigger": "manual"}, user_id=user_a.id)
    await session.commit()
    job = await queue.claim_next(session, clock.now())
    assert job is not None and job.run_after == clock.now()
