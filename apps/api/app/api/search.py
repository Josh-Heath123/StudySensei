import asyncio
import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser
from app.core.db import SessionDep
from app.schemas.search import SearchOut
from app.services.search.embedding import get_embedder
from app.services.search.search import search_module

router = APIRouter(tags=["search"])


@router.get("/modules/{module_id}/search", response_model=SearchOut)
async def search(
    module_id: uuid.UUID,
    q: Annotated[str, Query(min_length=1, max_length=500)],
    session: SessionDep,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
) -> SearchOut:
    """Search the module's materials by meaning and by words (hybrid, reciprocal rank fusion).

    Each result is one chunk of one page. `indexed_chunks` is 0 until a material is indexed.
    """
    embedder = await asyncio.to_thread(get_embedder)  # loads the model on first use
    found = await search_module(
        session, module_id, q, user_id=user.id, embedder=embedder, limit=limit
    )
    return SearchOut.model_validate(
        {"query": q.strip(), "results": found.hits, "indexed_chunks": found.indexed_chunks}
    )
