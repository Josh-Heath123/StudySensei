from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.core.config import get_settings
from app.core.db import SessionDep
from app.schemas.ai import AIStatusOut
from app.services.ai_status import ai_status

router = APIRouter(tags=["ai"])


@router.get("/ai/status", response_model=AIStatusOut)
async def status(session: SessionDep, user: CurrentUser) -> AIStatusOut:
    """Which AI providers have a key (yes/no only), each role's models, and today's usage.

    Usage counts the current user's requests since each provider's daily quota reset.
    """
    return await ai_status(session, get_settings(), user_id=user.id)
