"""Migration 0024 (reminders and the calendar feed, decision 0024): down and up again, its
constraints, and the schema guard's expectations for the new tables."""

import asyncio
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import UniqueConstraint
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.config import get_settings
from app.models import Base, CalendarFeed, PushSubscription, ReminderSent, User

CONFIG = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
TABLES = ("push_subscriptions", "reminders_sent", "calendar_feeds")


async def _present() -> dict[str, bool]:
    url = make_url(get_settings().database_url)
    connection = await asyncpg.connect(
        user=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        database=url.database,
    )
    try:
        found = {
            name: bool(await connection.fetchval("SELECT to_regclass($1) IS NOT NULL", name))
            for name in TABLES
        }
        found["users.reminder_minutes"] = bool(
            await connection.fetchval(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'users' AND column_name = 'reminder_minutes'"
            )
        )
        return found
    finally:
        await connection.close()


def test_0024_goes_down_and_up(migrated_db: None) -> None:
    command.downgrade(CONFIG, "0023")
    try:
        assert not any(asyncio.run(_present()).values())
    finally:
        command.upgrade(CONFIG, "head")
    assert all(asyncio.run(_present()).values())


def test_the_new_tables_have_their_unique_keys() -> None:
    tables = {table.name: table for table in Base.metadata.sorted_tables}

    def uniques(name: str) -> set[tuple[str, ...]]:
        return {
            tuple(c.name for c in constraint.columns)
            for constraint in tables[name].constraints
            if isinstance(constraint, UniqueConstraint)
        }

    assert uniques("push_subscriptions") == {("id", "user_id"), ("user_id", "endpoint")}
    assert uniques("reminders_sent") == {("user_id", "slot_key")}
    assert uniques("calendar_feeds") == {("user_id",), ("token_hash",)}
    for name in TABLES:
        assert tables[name].c.user_id.foreign_keys, name


async def test_a_reminder_lead_is_one_of_the_choices(session: AsyncSession, user_a: User) -> None:
    assert user_a.reminder_minutes == 10
    user_a.reminder_minutes = None
    await session.commit()
    user_a.reminder_minutes = 20
    with pytest.raises(IntegrityError, match="ck_users_reminder_minutes"):
        await session.commit()


async def test_an_endpoint_must_be_https(session: AsyncSession, user_a: User) -> None:
    session.add(
        PushSubscription(
            user_id=user_a.id, endpoint="http://push.example/x", p256dh="k", auth="a", label="x"
        )
    )
    with pytest.raises(IntegrityError, match="ck_push_subscriptions_https"):
        await session.commit()


async def test_one_reminder_per_slot_and_one_feed_per_user(
    session: AsyncSession, user_a: User, user_b: User
) -> None:
    now = clock.now()
    a, b = user_a.id, user_b.id  # the rollbacks below expire the users
    session.add_all(
        [
            ReminderSent(user_id=a, slot_key="a" * 64, sent_at=now),
            ReminderSent(user_id=b, slot_key="a" * 64, sent_at=now),  # another user's
            CalendarFeed(user_id=a, token_hash="b" * 64),
        ]
    )
    await session.commit()
    session.add(ReminderSent(user_id=a, slot_key="a" * 64, sent_at=now))
    with pytest.raises(IntegrityError, match="uq_reminders_sent_user_slot"):
        await session.commit()
    await session.rollback()
    session.add(CalendarFeed(user_id=a, token_hash="c" * 64))
    with pytest.raises(IntegrityError, match="uq_calendar_feeds_user"):
        await session.commit()
    await session.rollback()
    session.add(CalendarFeed(user_id=b, token_hash="b" * 64))
    with pytest.raises(IntegrityError, match="uq_calendar_feeds_token_hash"):
        await session.commit()
