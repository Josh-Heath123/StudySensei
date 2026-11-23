"""Migration 0027 (the AI marking a review was graded with, ADR 0029): down and up again,
and its check."""

import asyncio
from pathlib import Path

import asyncpg
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.models import Base

CONFIG = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))


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
        return {
            "column": bool(
                await connection.fetchval(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = 'reviews' AND column_name = 'ai_marking'"
                )
            ),
            "check": bool(
                await connection.fetchval(
                    "SELECT 1 FROM pg_constraint WHERE conname = 'ck_reviews_ai_marking'"
                )
            ),
            # 0025's, untouched.
            "trigger": bool(
                await connection.fetchval(
                    "SELECT 1 FROM pg_trigger WHERE tgname = 'trg_reviews_append_only'"
                )
            ),
        }
    finally:
        await connection.close()


def test_0027_goes_down_and_up(migrated_db: None) -> None:
    command.downgrade(CONFIG, "0026")
    try:
        assert asyncio.run(_present()) == {"column": False, "check": False, "trigger": True}
    finally:
        command.upgrade(CONFIG, "head")
    assert asyncio.run(_present()) == {"column": True, "check": True, "trigger": True}


def test_marked_by_ai_needs_a_marking_in_the_database_too() -> None:
    table = {t.name: t for t in Base.metadata.sorted_tables}["reviews"]
    checks = {c.name: str(c.sqltext) for c in table.constraints if c.name}
    assert checks["ck_reviews_ai_marking"] == "marked_by <> 'ai' OR ai_marking IS NOT NULL"
