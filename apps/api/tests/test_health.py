from collections.abc import AsyncIterator

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import get_session
from app.main import app


async def _get(path: str) -> tuple[int, dict[str, object]]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(path)
    return response.status_code, response.json()


async def test_health_ok_with_real_database() -> None:
    status, body = await _get("/health")

    assert status == 200
    assert body == {"status": "ok", "api": "ok", "database": "ok", "database_error": None}


async def test_health_reports_database_down() -> None:
    # Nothing listens on port 1, so the connection is refused straight away.
    engine = create_async_engine("postgresql+asyncpg://nobody:nothing@127.0.0.1:1/none")

    async def unreachable_session() -> AsyncIterator[AsyncSession]:
        async with async_sessionmaker(engine)() as session:
            yield session

    app.dependency_overrides[get_session] = unreachable_session
    try:
        status, body = await _get("/health")
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()

    assert status == 503
    assert body["api"] == "ok"
    assert body["database"] == "error"
    assert body["status"] == "degraded"
