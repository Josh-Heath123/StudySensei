"""HTTP test clients that act as a given user, against the rolled-back test session."""

import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LLMClient, set_llm_client
from app.ai.usage import DbUsageStore
from app.api.deps import get_current_user
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.main import app
from app.models import User
from app.storage.local import LocalStorage, get_storage
from tests.academics.conftest import Rows, make_rows
from tests.ai.conftest import routes, shared_session
from tests.fakes import FakeLLM

# Only the test app reads this header; the real get_current_user ignores it.
TEST_USER_HEADER = "X-Test-User"

ClientFactory = Callable[[User], AbstractAsyncContextManager[AsyncClient]]


@pytest.fixture
async def client_as(session: AsyncSession) -> AsyncIterator[ClientFactory]:
    async def test_session() -> AsyncIterator[AsyncSession]:
        yield session

    async def test_user(request: Request) -> User:
        user = await session.get(User, uuid.UUID(request.headers[TEST_USER_HEADER]))
        assert user is not None
        return user

    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[get_current_user] = test_user

    @asynccontextmanager
    async def factory(user: User) -> AsyncIterator[AsyncClient]:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={TEST_USER_HEADER: str(user.id)},
        ) as client:
            yield client

    try:
        yield factory
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
async def alice_api(client_as: ClientFactory, user_a: User) -> AsyncIterator[AsyncClient]:
    async with client_as(user_a) as client:
        yield client


@pytest.fixture
async def bob_api(client_as: ClientFactory, user_b: User) -> AsyncIterator[AsyncClient]:
    async with client_as(user_b) as client:
        yield client


@pytest.fixture
async def alice(session: AsyncSession, user_a: User) -> Rows:
    return await make_rows(session, user_a)


@pytest.fixture
async def bob(session: AsyncSession, user_b: User) -> Rows:
    return await make_rows(session, user_b)


@pytest.fixture(autouse=True)
def storage(tmp_path: Path) -> Iterator[LocalStorage]:
    """Uploaded files go to a temporary folder, never data/materials."""
    store = LocalStorage(tmp_path / "storage")
    app.dependency_overrides[get_storage] = lambda: store
    yield store
    app.dependency_overrides.pop(get_storage, None)


# Fake keys: only the fake transport ever sees them.
PING_GEMINI_KEY = "fake-gemini-key-for-ping-tests"
PING_GROQ_KEY = "fake-groq-key-for-ping-tests"


def ping_settings(*, keys: bool = True) -> Settings:
    """Two providers, three short-named models; Flash's budget is two a day."""
    return get_settings().model_copy(
        update={
            "gemini_api_key": SecretStr(PING_GEMINI_KEY) if keys else None,
            "groq_api_key": SecretStr(PING_GROQ_KEY) if keys else None,
            "ollama_model": None,
            "ai_smart": routes("gemini/flash", "groq/oss-120b"),
            "ai_bulk": routes("gemini/flash-lite", "groq/oss-120b"),
            "ai_vision": routes("gemini/flash"),
            "ai_long": routes("gemini/flash-lite"),
            "ai_daily_budget": {"gemini/flash": 2, "gemini/flash-lite": 100},
        }
    )


@pytest.fixture
def ping_llm(session: AsyncSession) -> Iterator[FakeLLM]:
    """The process's LLM client on a fake transport, logging usage into the test session."""
    fake = FakeLLM()
    usage = DbUsageStore(shared_session(session))
    set_llm_client(LLMClient(ping_settings(), usage, transport=fake.transport))
    yield fake
    set_llm_client(None)
