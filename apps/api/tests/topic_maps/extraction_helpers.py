import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TopicProposal


async def proposal_of(session: AsyncSession, material_id: uuid.UUID) -> dict[str, Any]:
    found = await session.scalar(
        select(TopicProposal.topics).where(TopicProposal.material_id == material_id)
    )
    assert found is not None, "no proposal saved"
    return dict(found)
