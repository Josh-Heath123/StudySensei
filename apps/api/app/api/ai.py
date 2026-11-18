from fastapi import APIRouter

from app.ai.client import get_llm_client
from app.api.deps import CurrentUser
from app.core.config import get_settings
from app.core.db import SessionDep
from app.schemas.ai import AIPingOut, AIStatusOut
from app.services.ai_status import ai_status, ping_models

router = APIRouter(tags=["ai"])


@router.get("/ai/status", response_model=AIStatusOut)
async def status(session: SessionDep, user: CurrentUser) -> AIStatusOut:
    """Which AI providers have a key (yes/no only), each role's models, and today's usage.

    Usage counts the current user's requests since each provider's daily quota reset.
    """
    return await ai_status(session, get_settings(), user_id=user.id)


@router.post("/ai/ping", response_model=AIPingOut)
async def ping(user: CurrentUser) -> AIPingOut:
    """Test every configured model with one short request each, all at once.

    A model whose daily budget is used up isn't called. Each call is logged in ai_usage
    (purpose "ping") against the current user. Errors carry the provider's text, never a key.
    """
    return await ping_models(get_llm_client(), user_id=user.id)
