"""What every eval runner shares: config files, a read-only dev-database session, the module.

The evals run locally against the dev database (Joshua's real data), never in CI, and
never call an AI provider. The session is read-only in Postgres itself
(``default_transaction_read_only``), so a runner can't write even by mistake.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import get_settings
from app.models import Module

EVALS_DIR = Path(__file__).resolve().parent


def load_config(relative: str) -> Any:
    """A YAML file under evals/, e.g. ``"search/cos330.yaml"``."""
    with (EVALS_DIR / relative).open(encoding="utf-8") as file:
        return yaml.safe_load(file)


@asynccontextmanager
async def dev_session() -> AsyncIterator[AsyncSession]:
    """A read-only session on the database in apps/api/.env (the dev database)."""
    url = get_settings().database_url
    if (make_url(url).database or "").endswith("_test"):
        raise SystemExit(f"The evals read the dev database, not {make_url(url).database}.")
    engine = create_async_engine(
        url, connect_args={"server_settings": {"default_transaction_read_only": "on"}}
    )
    try:
        async with AsyncSession(engine) as session:
            yield session
    finally:
        await engine.dispose()


async def find_module(session: AsyncSession, code: str) -> tuple[uuid.UUID, uuid.UUID]:
    """(module id, user id) of the one module with this code."""
    rows = (
        await session.execute(select(Module.id, Module.user_id).where(Module.code == code))
    ).all()
    if len(rows) != 1:
        raise SystemExit(f"Expected one module with code {code!r}, found {len(rows)}.")
    module_id, user_id = rows[0]
    return module_id, user_id
