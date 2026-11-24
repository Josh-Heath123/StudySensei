"""A review queues a re-plan (trigger "practice", ADR 0031) 15 minutes later, and a sitting of
reviews leaves one; migration 0028 (the trigger and the low_mastery reason) down and up."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import asyncpg
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.jobs.queue import enqueue_replan
from app.models import Job, User
from app.schemas.practice import ItemCreate, ReviewIn
from app.services.practice import items
from app.services.practice.reviewing import REPLAN_AFTER, review_item
from tests.practice.conftest import Practice

CONFIG = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
T0 = datetime(2026, 11, 2, 6, 0, tzinfo=UTC)


async def queued_replans(session: AsyncSession, user: User) -> list[Job]:
    return list(
        await session.scalars(
            select(Job)
            .where(Job.user_id == user.id, Job.kind == "replan", Job.status == "queued")
            .execution_options(populate_existing=True)
        )
    )


async def five_cards(session: AsyncSession, practice: Practice) -> list[uuid.UUID]:
    out: list[uuid.UUID] = []
    for n in range(5):
        created = await items.create_item(
            session,
            ItemCreate(
                module_id=practice.module_id,
                topic_id=practice.chapter,
                kind="flashcard",
                prompt=f"What is idea number {n}?",
                answer="An answer.",
            ),
            user_id=practice.user_id,
        )
        out.append(created.id)
    return out


async def test_five_reviews_leave_one_replan_15_minutes_after_the_first(
    session: AsyncSession, practice: Practice, user_a: User
) -> None:
    assert timedelta(minutes=15) == REPLAN_AFTER
    for n, item_id in enumerate(await five_cards(session, practice)):
        at = T0 + timedelta(minutes=n)
        await review_item(session, item_id, ReviewIn(grade=3), user_id=user_a.id, now=at)

    [job] = await queued_replans(session, user_a)
    assert job.payload == {"trigger": "practice", "detail": {}}
    # The earliest time is kept: 15 minutes after the first review.
    assert job.run_after == T0 + timedelta(minutes=15)


async def test_a_change_that_needs_a_replan_now_still_gets_it_now(
    session: AsyncSession, practice: Practice, user_a: User
) -> None:
    [item_id, *_] = await five_cards(session, practice)
    await review_item(session, item_id, ReviewIn(grade=1), user_id=user_a.id, now=T0)
    sooner = T0 + timedelta(minutes=2)
    await enqueue_replan(session, user_id=user_a.id, trigger="availability", run_after=sooner)
    await session.commit()

    [job] = await queued_replans(session, user_a)
    # Folded in: the first trigger, and the earlier time.
    assert (job.payload["trigger"], job.run_after) == ("practice", sooner)
    # A later one doesn't push it back.
    await enqueue_replan(
        session, user_id=user_a.id, trigger="availability", run_after=T0 + timedelta(hours=1)
    )
    await session.commit()
    [job] = await queued_replans(session, user_a)
    assert job.run_after == sooner


async def _checks() -> dict[str, str]:
    url = make_url(get_settings().database_url)
    connection = await asyncpg.connect(
        user=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        database=url.database,
    )
    try:
        rows = await connection.fetch(
            "SELECT conname, pg_get_constraintdef(oid) AS def FROM pg_constraint "
            "WHERE conname IN ('ck_plan_versions_trigger', 'ck_plan_blocks_reason')"
        )
        return {row["conname"]: row["def"] for row in rows}
    finally:
        await connection.close()


def test_0028_goes_down_and_up(migrated_db: None) -> None:
    command.downgrade(CONFIG, "0027")
    try:
        down = asyncio.run(_checks())
        assert "'practice'" not in down["ck_plan_versions_trigger"]
        assert "'move'" in down["ck_plan_versions_trigger"]
        assert "'low_mastery'" not in down["ck_plan_blocks_reason"]
        assert "'low_confidence'" in down["ck_plan_blocks_reason"]
    finally:
        command.upgrade(CONFIG, "head")
    up = asyncio.run(_checks())
    assert "'practice'" in up["ck_plan_versions_trigger"]
    assert "'low_mastery'" in up["ck_plan_blocks_reason"]
