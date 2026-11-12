import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.models import User


async def test_current_user_is_the_seeded_local_user(session: AsyncSession) -> None:
    local = User(email=get_settings().local_user_email, display_name="Local student")
    session.add(local)
    await session.flush()

    assert (await get_current_user(session)).id == local.id


async def test_missing_local_user_gives_503(session: AsyncSession) -> None:
    with pytest.raises(HTTPException) as exc:
        await get_current_user(session)

    assert exc.value.status_code == 503
    assert "db:seed" in str(exc.value.detail)
