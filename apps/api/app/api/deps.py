"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionDep
from app.models import User


async def get_current_user(session: SessionDep) -> User:
    """The signed-in user. Until Phase 9 (auth) this is the single seeded local user."""
    email = get_settings().local_user_email
    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Local user not found. Run `npm run db:seed`.",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
