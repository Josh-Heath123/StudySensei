import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from tests.academics.conftest import Rows, make_rows


@pytest.fixture
async def alice(session: AsyncSession, user_a: User) -> Rows:
    return await make_rows(session, user_a)


@pytest.fixture
async def bob(session: AsyncSession, user_b: User) -> Rows:
    return await make_rows(session, user_b)
