"""Migration 0025 (practice items, ADR 0025): down and up again, the keys the schema guard
expects, and the constraints Postgres enforces, including that no item can cite another
user's chunk."""

import asyncio
import uuid
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import UniqueConstraint
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Base, PracticeItem, PracticeItemSource, User
from app.services.practice.filter import prompt_key
from tests.practice.conftest import Practice, make_practice

CONFIG = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
TABLES = ("practice_generations", "practice_items", "practice_item_sources", "reviews")


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
        found["trigger"] = bool(
            await connection.fetchval(
                "SELECT 1 FROM pg_trigger WHERE tgname = 'trg_reviews_append_only'"
            )
        )
        return found
    finally:
        await connection.close()


def test_0025_goes_down_and_up(migrated_db: None) -> None:
    command.downgrade(CONFIG, "0024")
    try:
        assert not any(asyncio.run(_present()).values())
    finally:
        command.upgrade(CONFIG, "head")
    assert all(asyncio.run(_present()).values())


def test_the_keys() -> None:
    tables = {table.name: table for table in Base.metadata.sorted_tables}

    def uniques(name: str) -> set[tuple[str, ...]]:
        return {
            tuple(c.name for c in constraint.columns)
            for constraint in tables[name].constraints
            if isinstance(constraint, UniqueConstraint)
        }

    assert uniques("practice_items") == {("id", "user_id")}
    assert uniques("practice_generations") == {("id", "user_id")}
    assert [c.name for c in tables["practice_item_sources"].primary_key] == ["item_id", "chunk_id"]
    indexes = {str(index.name): index for index in tables["practice_items"].indexes}
    one = indexes["uq_practice_items_topic_prompt"]
    assert one.unique and [c.name for c in one.columns] == ["user_id", "topic_id", "prompt_key"]
    active = {str(i.name): i for i in tables["practice_generations"].indexes}
    assert active["uq_practice_generations_one_active"].unique
    review_index = {str(i.name): i for i in tables["reviews"].indexes}["ix_reviews_user_item_at"]
    assert [c.name for c in review_index.columns] == ["user_id", "item_id", "reviewed_at"]


def an_item(practice: Practice, **kw: Any) -> PracticeItem:
    base: dict[str, Any] = {
        "id": uuid.uuid4(),
        "user_id": practice.user_id,
        "module_id": practice.module_id,
        "topic_id": practice.chapter,
        "kind": "flashcard",
        "prompt": "What is a firewall?",
        "answer": "A filter.",
        "origin": "user",
        "status": "active",
        "prompt_key": prompt_key("What is a firewall?"),
    }
    return PracticeItem(**{**base, **kw})


@pytest.mark.parametrize(
    ("changes", "constraint"),
    [
        ({"kind": "short_answer"}, "ck_practice_items_key_points"),
        ({"kind": "short_answer", "key_points": []}, "ck_practice_items_key_points"),
        ({"key_points": ["a"]}, "ck_practice_items_key_points"),
        (
            {"kind": "short_answer", "key_points": ["a", "b", "c", "d", "e", "f"]},
            "ck_practice_items_key_points",
        ),
        ({"status": "rejected"}, "ck_practice_items_reject_reason"),
        ({"reject_reason": "wrong"}, "ck_practice_items_reject_reason"),
        ({"origin": "ai"}, "ck_practice_items_ai_model"),
        ({"prompt": ""}, "ck_practice_items_prompt"),
        ({"answer": "x" * 1501}, "ck_practice_items_answer"),
    ],
)
async def test_item_constraints(
    session: AsyncSession, practice: Practice, changes: dict[str, Any], constraint: str
) -> None:
    session.add(an_item(practice, **changes))
    with pytest.raises(IntegrityError, match=constraint):
        await session.commit()


async def test_one_prompt_per_topic_unless_rejected(
    session: AsyncSession, practice: Practice
) -> None:
    session.add(an_item(practice))
    await session.commit()
    session.add(an_item(practice, status="rejected", reject_reason="duplicate"))
    await session.commit()
    session.add(an_item(practice, topic_id=None))  # no topic: no clash
    await session.commit()
    session.add(an_item(practice))
    with pytest.raises(IntegrityError, match="uq_practice_items_topic_prompt"):
        await session.commit()


async def test_no_item_can_cite_another_users_chunk(
    session: AsyncSession, practice: Practice, user_b: User
) -> None:
    bobs = await make_practice(session, user_b, "COS301")
    hers = practice.chunks["FIREWALL"]
    item = an_item(bobs)
    session.add(item)
    await session.commit()
    item_id = item.id
    # As Bob (his item, her chunk) or as Alice (her chunk, his item): the FK refuses both.
    for user_id in (bobs.user_id, practice.user_id):
        session.add(PracticeItemSource(item_id=item_id, chunk_id=hers, user_id=user_id, label="S1"))
        with pytest.raises(IntegrityError, match="fk"):
            await session.commit()
        await session.rollback()
    # His own chunk is fine.
    session.add(
        PracticeItemSource(
            item_id=item_id, chunk_id=bobs.chunks["FIREWALL"], user_id=bobs.user_id, label="S1"
        )
    )
    await session.commit()
