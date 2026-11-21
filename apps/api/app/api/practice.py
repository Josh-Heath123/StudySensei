"""Practice items, their generation and reviews (Phase 5, ADR 0025)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser
from app.core import clock
from app.core.db import SessionDep
from app.models import PracticeGeneration, Review
from app.schemas.practice import (
    GenerateIn,
    GenerationOut,
    ItemCreate,
    ItemOrigin,
    ItemOut,
    ItemPage,
    ItemStatus,
    ItemUpdate,
    ReviewIn,
    ReviewOut,
)
from app.services.practice import generation, items

router = APIRouter(tags=["practice"])


@router.post(
    "/topics/{topic_id}/practice/generate",
    response_model=GenerationOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate(
    topic_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
    data: GenerateIn | None = None,
) -> PracticeGeneration:
    """Queue the AI to write ``count`` items (4 to 12, default 8) from the topic's linked
    slides and notes (AI-allowed only). 409 while one is queued or running for the topic;
    422 when no eligible source is linked to it."""
    count = (data or GenerateIn()).count
    return await generation.request_generation(session, topic_id, count, user_id=user.id)


@router.get("/topics/{topic_id}/practice/generations", response_model=list[GenerationOut])
async def list_generations(
    topic_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> list[PracticeGeneration]:
    """The topic's last 10 generations, newest first."""
    return await generation.recent_generations(session, topic_id, user_id=user.id)


@router.get("/practice/items", response_model=ItemPage)
async def list_items(
    session: SessionDep,
    user: CurrentUser,
    module_id: uuid.UUID | None = None,
    topic_id: uuid.UUID | None = None,
    status: ItemStatus | None = None,
    origin: ItemOrigin | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ItemPage:
    """Your items, newest first, each with its sources (label, material, page)."""
    found, total = await items.list_items(
        session,
        items.ItemFilters(module_id=module_id, topic_id=topic_id, status=status, origin=origin),
        user_id=user.id,
        limit=limit,
        offset=offset,
    )
    return ItemPage(items=found, total=total)


@router.post("/practice/items", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
async def create_item(data: ItemCreate, session: SessionDep, user: CurrentUser) -> ItemOut:
    """Your own card or question (origin user)."""
    return await items.create_item(session, data, user_id=user.id)


@router.patch("/practice/items/{item_id}", response_model=ItemOut)
async def update_item(
    item_id: uuid.UUID, data: ItemUpdate, session: SessionDep, user: CurrentUser
) -> ItemOut:
    """Editing an AI item's text makes it yours (origin user); its sources stay. Rejecting
    needs a ``reject_reason``."""
    return await items.update_item(session, item_id, data, user_id=user.id)


@router.delete("/practice/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> None:
    await items.delete_item(session, item_id, user_id=user.id)


@router.post(
    "/practice/items/{item_id}/reviews",
    response_model=ReviewOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_review(
    item_id: uuid.UUID, data: ReviewIn, session: SessionDep, user: CurrentUser
) -> Review:
    """Record a self-marked answer: grade 1 (again) to 4 (easy). Reviews are never changed."""
    return await items.add_review(session, item_id, data, user_id=user.id, now=clock.now())


@router.get("/practice/items/{item_id}/reviews", response_model=list[ReviewOut])
async def list_reviews(item_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> list[Review]:
    """The item's reviews, newest first."""
    return await items.list_reviews(session, item_id, user_id=user.id)
