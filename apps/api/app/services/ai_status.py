"""GET /ai/status (providers, roles and today's usage against each budget) and POST /ai/ping."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.budget import next_reset, quota_zone, window_start
from app.ai.client import LLMClient
from app.ai.ping import ping_routes
from app.ai.routes import ROLES, all_routes, providers, routes_for
from app.ai.usage import count_requests
from app.core.config import Settings
from app.schemas.ai import (
    AIModelStatus,
    AIPingOut,
    AIPingResult,
    AIProviderStatus,
    AIStatusOut,
)


async def ai_status(
    session: AsyncSession, settings: Settings, *, user_id: uuid.UUID, now: datetime | None = None
) -> AIStatusOut:
    now = now or datetime.now(UTC)
    provider_rows = [
        AIProviderStatus(
            name=provider.name, configured=provider.configured, key_set=provider.api_key is not None
        )
        for provider in providers(settings).values()
    ]
    models = []
    for route in all_routes(settings):
        zone = quota_zone(route.provider.name, settings)
        used = await count_requests(
            session,
            user_id=user_id,
            provider=route.provider.name,
            model=route.model,
            since=window_start(now, zone),
        )
        models.append(
            AIModelStatus(
                provider=route.provider.name,
                model=route.model,
                configured=route.configured,
                vision=route.vision,
                daily_budget=route.daily_budget,
                used_today=used,
                resets_at=next_reset(now, zone) if route.daily_budget is not None else None,
            )
        )
    return AIStatusOut(
        available=any(p.configured for p in provider_rows),
        providers=provider_rows,
        roles={role: [route.key for route in routes_for(role, settings)] for role in ROLES},
        models=models,
    )


async def ping_models(client: LLMClient, *, user_id: uuid.UUID) -> AIPingOut:
    """Test every configured model once, at the same time; usage is logged for ``user_id``."""
    routes = [route for route in all_routes(client.settings) if route.configured]
    outcomes = await ping_routes(client, routes, user_id=user_id)
    return AIPingOut(
        results=[
            AIPingResult(
                provider=o.route.provider.name,
                model=o.route.model,
                status=o.status,
                latency_ms=o.latency_ms,
                error=o.error,
                resets_at=o.resets_at,
                in_models_list=o.listed,
                models_list_error=o.list_error,
            )
            for o in outcomes
        ]
    )
