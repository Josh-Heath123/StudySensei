import asyncio
import os

from tests.xdist_db import worker_database_url

# Point every test at the test database before app settings are first read.
# CI sets DATABASE_URL itself; locally this defaults to the docker-compose db.
os.environ["DATABASE_URL"] = worker_database_url(
    os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://studysensei:studysensei@localhost:5433/studysensei_test",
    ),
    os.environ.get("PYTEST_XDIST_WORKER"),
)
# Real AI keys in apps/api/.env are ignored: environment variables beat the .env file, and
# blank means unset. So the Stop hook and CI never call a real provider (see no_real_llm).
os.environ["GEMINI_API_KEY"] = ""
os.environ["GROQ_API_KEY"] = ""
os.environ["OLLAMA_MODEL"] = ""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import asyncpg
import httpx
import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.ai.client import LLMClient, set_llm_client
from app.ai.usage import UsageRecord
from app.core.config import get_settings
from app.models import User
from app.services.push.sender import FakePushSender, set_sender
from app.services.search.embedding import FastEmbedder, set_embedder
from tests.fakes import FakeEmbedder, refuse_network

API_DIR = Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    return Config(str(API_DIR / "alembic.ini"))


async def _create_database(url: str) -> None:
    """Create the database if it's missing (a new xdist worker's), via the server's postgres db."""
    parsed = make_url(url)
    connection = await asyncpg.connect(
        user=parsed.username,
        password=parsed.password,
        host=parsed.host,
        port=parsed.port,
        database="postgres",
    )
    try:
        exists = await connection.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", parsed.database
        )
        if not exists:
            await connection.execute(f'CREATE DATABASE "{parsed.database}"')
    finally:
        await connection.close()


@pytest.fixture(scope="session")
def migrated_db() -> None:
    """Rebuild the test schema from scratch once per run (also exercises downgrades)."""
    database = make_url(get_settings().database_url).database or ""
    # The downgrade drops every table, so never let it near a real database.
    if not database.endswith("_test"):
        raise RuntimeError(f"Refusing to run tests against '{database}': name must end in _test")
    asyncio.run(_create_database(get_settings().database_url))
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


@pytest.fixture(scope="session")
def real_model() -> FastEmbedder:
    """The real embedding model, loaded once per run (downloaded on the first ever run)."""
    return FastEmbedder(get_settings().models_dir)


@pytest.fixture(autouse=True)
def fake_embedder(request: pytest.FixtureRequest) -> Iterator[FakeEmbedder | None]:
    """Every test embeds with FakeEmbedder, except those marked ``real_embedder``."""
    if request.node.get_closest_marker("real_embedder") is not None:
        set_embedder(request.getfixturevalue("real_model"))
        yield None
    else:
        fake = FakeEmbedder()
        set_embedder(fake)
        yield fake
    set_embedder(None)


class _NoUsage:
    async def count_since(self, **_: object) -> int:
        return 0

    async def record(self, row: UsageRecord) -> None:
        pass


@pytest.fixture(autouse=True)
def no_real_llm() -> Iterator[None]:
    """The process's LLM client has no keys, and its transport fails any request.

    Tests that exercise AI build their own client on a ``FakeLLM`` transport.
    """
    settings = get_settings()
    assert settings.gemini_api_key is None and settings.groq_api_key is None
    client = LLMClient(settings, _NoUsage(), transport=httpx.MockTransport(refuse_network))
    set_llm_client(client)
    yield
    set_llm_client(None)


@pytest.fixture(autouse=True)
def fake_push(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakePushSender]:
    """Push never reaches the network: every test sends through a FakePushSender, and push is
    off (no VAPID keys) unless a test turns it on with ``push_on``."""
    settings = get_settings()
    for name in ("vapid_public_key", "vapid_private_key", "vapid_subject"):
        monkeypatch.setattr(settings, name, None)
    fake = FakePushSender()
    set_sender(fake)
    yield fake
    set_sender(None)


@pytest.fixture
def push_on(monkeypatch: pytest.MonkeyPatch, fake_push: FakePushSender) -> FakePushSender:
    """VAPID keys set (made up: the fake sender never signs anything)."""
    settings = get_settings()
    monkeypatch.setattr(settings, "vapid_public_key", "BPublicKeyForTests")
    monkeypatch.setattr(settings, "vapid_private_key", SecretStr("private-key-for-tests"))
    monkeypatch.setattr(settings, "vapid_subject", "mailto:tests@example.com")
    return fake_push
