import os

# Point every test at the test database before app settings are first read.
# CI sets DATABASE_URL itself; locally this defaults to the docker-compose db.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://studysensei:studysensei@localhost:5433/studysensei_test",
)

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.core.config import get_settings
from app.models import User

API_DIR = Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    return Config(str(API_DIR / "alembic.ini"))


@pytest.fixture(scope="session")
def migrated_db() -> None:
    """Rebuild the test schema from scratch once per run (also exercises downgrades)."""
    database = make_url(get_settings().database_url).database or ""
    # The downgrade drops every table, so never let it near a real database.
    if not database.endswith("_test"):
        raise RuntimeError(f"Refusing to run tests against '{database}': name must end in _test")
    config = _alembic_config()
    command.downgrade(config, "base")
    command.upgrade(config, "head")


@pytest.fixture(scope="session")
async def engine(migrated_db: None) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(get_settings().database_url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session whose work is rolled back after each test.

    Service code calls commit(); with create_savepoint those commits only
    release a savepoint inside the outer transaction we roll back here.
    """
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()


async def _make_user(session: AsyncSession, name: str) -> User:
    user = User(email=f"{name}@example.test", display_name=name.title())
    session.add(user)
    await session.flush()
    return user


@pytest.fixture
async def user_a(session: AsyncSession) -> User:
    return await _make_user(session, "alice")


@pytest.fixture
async def user_b(session: AsyncSession) -> User:
    return await _make_user(session, "bob")
