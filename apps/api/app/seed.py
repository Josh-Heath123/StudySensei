"""Create the single local user. Safe to run repeatedly.

Run with: uv run python -m app.seed
"""

import asyncio

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.models import User


async def seed() -> None:
    email = get_settings().local_user_email
    async with get_sessionmaker()() as session:
        existing = await session.scalar(select(User).where(User.email == email))
        if existing is None:
            session.add(User(email=email, display_name="Local student"))
            await session.commit()
            print(f"Seeded local user {email}")
        else:
            print(f"Local user {email} already exists")
    await get_engine().dispose()


if __name__ == "__main__":
    asyncio.run(seed())
