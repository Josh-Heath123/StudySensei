"""Practice items, their generation and reviews (Phase 5, ADR 0025)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.ai.client import get_llm_client
from app.api.deps import CurrentUser
from app.core import clock
from app.core.db import SessionDep
from app.models import PracticeGeneration, Review
from app.schemas.practice import (
    AIMarking,
    GenerateIn,
    GenerationOut,
    ItemCreate,
    ItemKind,
    ItemOrigin,
    ItemOut,
    ItemPage,
    ItemStatus,
    ItemUpdate,
    MarkIn,
    PracticeSettingsOut,
    PracticeSettingsUpdate,
    PreviewOut,
    QueueOut,
    ReviewIn,
    ReviewOut,
    ReviewResultOut,
    ScheduledOut,
)
from app.services.practice import generation, items, marking, queue, reviewing

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
    kind: ItemKind | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ItemPage:
    """Your items, newest first, each with its sources (label, material, page)."""
    found, total = await items.list_items(
        session,
        items.ItemFilters(
            module_id=module_id, topic_id=topic_id, status=status, origin=origin, kind=kind
        ),
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
    response_model=ReviewResultOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_review(
    item_id: uuid.UUID, data: ReviewIn, session: SessionDep, user: CurrentUser
) -> ReviewResultOut:
    """Record an answer's grade, 1 (again) to 4 (easy), and schedule the item with FSRS. The
    student always chooses the grade: ``marked_by`` is "ai" only when it's the grade an AI
    marking suggested, sent back as ``ai_marking`` (422 otherwise, or when the marking doesn't
    fit the item). 409 for a suspended or rejected item. Returns the review, the new due time
    and the queue's counts. Reviews are never changed."""
    now = clock.now()
    done = await reviewing.review_item(session, item_id, data, user_id=user.id, now=now)
    review = ReviewOut.model_validate(done.review)
    counts = await queue.queue_counts(session, user_id=user.id, now=now)
    return ReviewResultOut(
        review=review,
        scheduled=ScheduledOut(
            state=done.state.state, due=done.state.due, scheduled_days=done.scheduled_days
        ),
        counts=counts,
    )


@router.post(
    "/practice/items/{item_id}/mark",
    response_model=AIMarking,
    responses={
        502: {"description": "The AI's marking couldn't be used; mark it yourself"},
        503: {"description": "No AI model can take it now; Retry-After says when to try again"},
    },
)
async def mark(
    item_id: uuid.UUID, data: MarkIn, session: SessionDep, user: CurrentUser
) -> AIMarking:
    """Ask the AI whether a short answer covers each of the item's key points (ADR 0029).

    Sends the question, the reference answer, its key points and your answer: nothing else
    about you. Code derives the verdict and the suggested grade (all covered: Good; at least
    half: Hard; fewer: Again); the AI never grades. Stores nothing. 422 for a flashcard; 409
    for a suspended or rejected item; 503 (with Retry-After) when every model is busy."""
    return await marking.mark_item(
        session, item_id, data.answer_text, user_id=user.id, client=get_llm_client()
    )


@router.get("/practice/items/{item_id}/preview", response_model=PreviewOut)
async def preview(item_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> PreviewOut:
    """For each grade, when the item would be due if reviewed now, and as a short label."""
    return await reviewing.preview(session, item_id, user_id=user.id, now=clock.now())


@router.get("/practice/queue", response_model=QueueOut)
async def review_queue(
    session: SessionDep,
    user: CurrentUser,
    module_id: uuid.UUID | None = None,
    topic_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=queue.MAX_LIMIT)] = queue.DEFAULT_LIMIT,
) -> QueueOut:
    """Due items (oldest due first), then new items up to today's allowance (oldest first),
    with the counts."""
    found, counts = await queue.review_queue(
        session,
        user_id=user.id,
        now=clock.now(),
        scope=queue.Scope(module_id=module_id, topic_id=topic_id),
        limit=limit,
    )
    return QueueOut(items=found, counts=counts)


@router.get("/practice/settings", response_model=PracticeSettingsOut)
async def get_settings(session: SessionDep, user: CurrentUser) -> PracticeSettingsOut:
    return await queue.get_settings(session, user_id=user.id)


@router.patch("/practice/settings", response_model=PracticeSettingsOut)
async def update_settings(
    data: PracticeSettingsUpdate, session: SessionDep, user: CurrentUser
) -> PracticeSettingsOut:
    """New items a day (0-200) and desired retention (0.80-0.97). A new retention applies to
    later reviews only."""
    return await queue.update_settings(session, data, user_id=user.id)


@router.get("/practice/items/{item_id}/reviews", response_model=list[ReviewOut])
async def list_reviews(item_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> list[Review]:
    """The item's reviews, newest first."""
    return await items.list_reviews(session, item_id, user_id=user.id)
