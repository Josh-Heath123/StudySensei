"""HTTP test clients that act as a given user, against the rolled-back test session."""

import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_session
from app.main import app
from app.models import User
from tests.academics.conftest import Rows, make_rows

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
