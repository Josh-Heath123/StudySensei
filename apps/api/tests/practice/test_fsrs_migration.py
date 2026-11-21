"""Migration 0026 (FSRS scheduling, ADR 0026): down and up again, and its constraints."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Base, PracticeItem, PracticeItemState, User
from app.services.practice.filter import prompt_key
from tests.practice.conftest import Practice

CONFIG = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
NOW = datetime(2026, 11, 2, 8, 0, tzinfo=UTC)


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
            "practice_item_states": bool(
                await connection.fetchval("SELECT to_regclass('practice_item_states') IS NOT NULL")
            )
        }
        for table, column in (
            ("reviews", "state_after"),
            ("reviews", "fsrs_version"),
            ("users", "practice_new_per_day"),
            ("users", "practice_desired_retention"),
        ):
            found[f"{table}.{column}"] = bool(
                await connection.fetchval(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = $1 AND column_name = $2",
                    table,
                    column,
                )
            )
        found["trigger"] = bool(
            await connection.fetchval(
                "SELECT 1 FROM pg_trigger WHERE tgname = 'trg_reviews_append_only'"
            )
        )
        return found
    finally:
        await connection.close()


def test_0026_goes_down_and_up(migrated_db: None) -> None:
    command.downgrade(CONFIG, "0025")
    try:
        found = asyncio.run(_present())
        assert found.pop("trigger")  # 0025's, untouched
        assert not any(found.values())
    finally:
        command.upgrade(CONFIG, "head")
    assert all(asyncio.run(_present()).values())


def test_the_state_table_is_keyed_by_its_item() -> None:
    table = {t.name: t for t in Base.metadata.sorted_tables}["practice_item_states"]
    assert [c.name for c in table.primary_key] == ["item_id"]
    [fk] = table.foreign_key_constraints
    assert (fk.referred_table.name, fk.column_keys, fk.ondelete) == (
        "practice_items",
        ["item_id", "user_id"],
        "CASCADE",
    )


def a_state(item_id: uuid.UUID, user_id: uuid.UUID, **kw: Any) -> PracticeItemState:
    base: dict[str, Any] = {
        "item_id": item_id,
        "user_id": user_id,
        "state": "review",
        "step": None,
        "stability": 3.0,
        "difficulty": 5.0,
        "due": NOW + timedelta(days=3),
        "last_review_at": NOW,
        "reps": 2,
        "lapses": 0,
    }
    return PracticeItemState(**{**base, **kw})


async def an_item(session: AsyncSession, practice: Practice) -> uuid.UUID:
    item = PracticeItem(
        user_id=practice.user_id,
        module_id=practice.module_id,
        kind="flashcard",
        prompt="What is a card?",
        answer="A card.",
        origin="user",
        status="active",
        prompt_key=prompt_key("What is a card?"),
    )
    session.add(item)
    await session.commit()
    return item.id


@pytest.mark.parametrize(
    ("changes", "constraint"),
    [
        ({"state": "new"}, "ck_practice_item_states_state"),
        ({"stability": 0.0}, "ck_practice_item_states_stability"),
        ({"difficulty": 11.0}, "ck_practice_item_states_difficulty"),
        ({"reps": 0}, "ck_practice_item_states_counts"),
        ({"lapses": -1}, "ck_practice_item_states_counts"),
        ({"due": NOW}, "ck_practice_item_states_due"),
        ({"step": -1}, "ck_practice_item_states_step"),
    ],
)
async def test_state_constraints(
    session: AsyncSession, practice: Practice, changes: dict[str, Any], constraint: str
) -> None:
    item_id = await an_item(session, practice)
    session.add(a_state(item_id, practice.user_id, **changes))
    with pytest.raises(IntegrityError, match=constraint):
        await session.commit()


async def test_a_state_cant_belong_to_another_users_item(
    session: AsyncSession, practice: Practice, user_b: User
) -> None:
    item_id = await an_item(session, practice)
    session.add(a_state(item_id, user_b.id))
    with pytest.raises(IntegrityError, match="fk"):
        await session.commit()


@pytest.mark.parametrize(
    ("column", "value", "constraint"),
    [
        ("practice_new_per_day", 201, "ck_users_practice_new_per_day"),
        ("practice_new_per_day", -1, "ck_users_practice_new_per_day"),
        ("practice_desired_retention", 0.79, "ck_users_practice_desired_retention"),
        ("practice_desired_retention", 0.98, "ck_users_practice_desired_retention"),
    ],
)
async def test_user_settings_ranges(
    session: AsyncSession, user_a: User, column: str, value: float, constraint: str
) -> None:
    assert (user_a.practice_new_per_day, user_a.practice_desired_retention) == (20, 0.9)
    setattr(user_a, column, value)
    with pytest.raises(IntegrityError, match=constraint):
        await session.commit()
