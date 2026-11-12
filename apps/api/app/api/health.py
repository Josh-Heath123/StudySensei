import asyncio
from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import SessionDep

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    api: Literal["ok"]
    database: Literal["ok", "error"]
    database_error: str | None = None


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse, "description": "Database unreachable"}},
)
async def health(response: Response, session: SessionDep) -> HealthResponse:
    """Report whether the API is up and can reach the database."""
    try:
        await asyncio.wait_for(
            session.execute(text("SELECT 1")),
            timeout=get_settings().health_db_timeout_seconds,
        )
    except Exception as exc:  # any failure means "database down" for this check
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        reason = "timed out" if isinstance(exc, TimeoutError) else type(exc).__name__
        return HealthResponse(status="degraded", api="ok", database="error", database_error=reason)
    return HealthResponse(status="ok", api="ok", database="ok")
