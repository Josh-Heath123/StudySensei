"""Migration 0022 (plan versions and blocks, decision 0021): down and up again, and the
composite FK that keeps a session's planned block the same user's."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import PlanBlock, PlanVersion, StudySession, User
from tests.academics.conftest import make_rows

CONFIG = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))


async def _schema() -> dict[str, bool]:
    url = make_url(get_settings().database_url)
    connection = await asyncpg.connect(
        user=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        database=url.database,
    )
    try:
        return {
            "plan_versions": bool(await connection.fetchval("SELECT to_regclass('plan_versions')")),
            "plan_blocks": bool(await connection.fetchval("SELECT to_regclass('plan_blocks')")),
            "replan index": bool(
                await connection.fetchval("SELECT to_regclass('uq_jobs_one_queued_replan')")
            ),
            "session fk": bool(
                await connection.fetchval(
                    "SELECT 1 FROM pg_constraint WHERE conname = "
                    "'fk_study_sessions_plan_block_id_user_id_plan_blocks'"
                )
            ),
        }
    finally:
        await connection.close()


def test_0022_goes_down_and_up(migrated_db: None) -> None:
    command.downgrade(CONFIG, "0021")
    try:
        assert not any(asyncio.run(_schema()).values())
    finally:
        command.upgrade(CONFIG, "head")
    assert all(asyncio.run(_schema()).values())


async def block_of(session: AsyncSession, user: User) -> PlanBlock:
    rows = await make_rows(session, user)
    now = datetime.now(UTC)
    version = PlanVersion(
        user_id=user.id,
        number=1,
        trigger="initial",
        summary="Your first plan.",
        generated_at=now,
        checked_at=now,
        days=28,
        report={},
    )
    session.add(version)
    await session.flush()
    block = PlanBlock(
        user_id=user.id,
        version_id=version.id,
        start_at=now + timedelta(hours=1),
        end_at=now + timedelta(hours=1, minutes=50),
        module_id=rows.module.id,
        assessment_id=rows.assessment.id,
        topic_id=rows.topic.id,
        kind="study",
        reason="workload",
        method="first_pass",
        reason_text="Why.",
        method_text="How.",
    )
    session.add(block)
    await session.commit()
    return block


async def test_a_session_cant_point_at_another_users_block(
    session: AsyncSession, user_a: User, user_b: User
) -> None:
    hers = await block_of(session, user_a)
    his = await make_rows(session, user_b, code="COS301")
    his.study_session.plan_block_id = hers.id
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_deleting_a_block_keeps_its_session(session: AsyncSession, user_a: User) -> None:
    block = await block_of(session, user_a)
    study = await session.get(
        StudySession, (await make_rows(session, user_a, "COS2")).study_session.id
    )
    assert study is not None
    study.plan_block_id = block.id
    await session.commit()
    await session.delete(block)
    await session.commit()
    await session.refresh(study)
    assert study.plan_block_id is None
    assert study.user_id == user_a.id


async def test_a_block_cant_use_another_users_topic(
    session: AsyncSession, user_a: User, user_b: User
) -> None:
    hers = await block_of(session, user_a)
    his = await make_rows(session, user_b, code="COS301")
    hers.topic_id = his.topic.id
    with pytest.raises(IntegrityError):
        await session.commit()
