"""Practice items and their reviews (ADR 0025). Every query is scoped by ``user_id``.

- The student's own items are origin ``user``. Editing an AI item's prompt, answer or key
  points makes it the student's too (as with topics, decision 0009); its sources stay.
- A rejected item carries its reason; un-rejecting clears it. Prompts are unique per topic
  among items that aren't rejected (Postgres decides: a clash is a ``Conflict``).
- Reviews are append-only: added and listed, never changed (Postgres refuses an UPDATE).
- ``move_items`` is the topic merge's part (decision 0009): the topic's items go to the
  target, and any whose prompt the target already has are rejected as duplicates.
"""

import uuid
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.models import (
    Chunk,
    Material,
    PracticeItem,
    PracticeItemSource,
    PracticeItemState,
    Review,
    Topic,
)
from app.schemas.practice import (
    Estimate,
    ItemCreate,
    ItemOut,
    ItemPageOut,
    ItemSourceOut,
    ItemUpdate,
    MemoryOut,
)
from app.services.academics.modules import get_module
from app.services.errors import Conflict, Invalid, NotFound
from app.services.practice.filter import prompt_key
from app.services.practice.scheduling import MemoryState, retrievability

DUPLICATE = "This topic already has a card or question with that prompt."
TEXT_FIELDS = ("prompt", "answer", "key_points")


@dataclass(frozen=True)
class ItemFilters:
    module_id: uuid.UUID | None = None
    topic_id: uuid.UUID | None = None
    status: str | None = None
    origin: str | None = None
    kind: str | None = None


async def get_item(
    session: AsyncSession, item_id: uuid.UUID, *, user_id: uuid.UUID
) -> PracticeItem:
    item = await session.scalar(
        select(PracticeItem).where(PracticeItem.id == item_id, PracticeItem.user_id == user_id)
    )
    if item is None:
        raise NotFound("Practice item")
    return item


async def sources_of(
    session: AsyncSession, item_ids: list[uuid.UUID], *, user_id: uuid.UUID
) -> dict[uuid.UUID, list[ItemSourceOut]]:
    """Each item's cited sources (label, material, page), in label order."""
    found: dict[uuid.UUID, list[ItemSourceOut]] = defaultdict(list)
    if not item_ids:
        return found
    rows = await session.execute(
        select(
            PracticeItemSource.item_id,
            PracticeItemSource.label,
            Material.id,
            Material.title,
            Chunk.page_number,
        )
        .join(
            Chunk,
            (Chunk.id == PracticeItemSource.chunk_id)
            & (Chunk.user_id == PracticeItemSource.user_id),
        )
        .join(Material, (Material.id == Chunk.material_id) & (Material.user_id == Chunk.user_id))
        .where(PracticeItemSource.user_id == user_id, PracticeItemSource.item_id.in_(item_ids))
    )
    for item_id, label, material_id, title, page in rows:
        found[item_id].append(
            ItemSourceOut(
                label=label, material_id=material_id, material_title=title, page_number=page
            )
        )
    for sources in found.values():
        sources.sort(key=lambda s: int(s.label[1:]))
    return found


def distinct_pages(sources: list[ItemSourceOut]) -> list[ItemPageOut]:
    """Each (material, page) once, in label order."""
    pages = dict.fromkeys((s.material_id, s.material_title, s.page_number) for s in sources)
    return [ItemPageOut(material_id=m, material_title=t, page_number=n) for m, t, n in pages]


def memory_out(row: PracticeItemState | None, now: datetime) -> MemoryOut:
    """Where an item stands in FSRS now (decision 0026). No state row: a new item."""
    if row is None:
        return MemoryOut(
            state="new",
            due=None,
            stability=None,
            difficulty=None,
            retrievability=None,
            reps=0,
            lapses=0,
        )
    state = memory_state(row)
    chance = retrievability(state, now)
    return MemoryOut(
        state=state.state,
        due=state.due,
        stability=state.stability,
        difficulty=state.difficulty,
        retrievability=(
            Estimate(value=round(chance, 4), sample_size=state.reps) if chance is not None else None
        ),
        reps=state.reps,
        lapses=state.lapses,
    )


def memory_state(row: PracticeItemState) -> MemoryState:
    return MemoryState(
        state=row.state,  # type: ignore[arg-type]
        step=row.step,
        stability=row.stability,
        difficulty=row.difficulty,
        due=row.due,
        last_review_at=row.last_review_at,
        reps=row.reps,
        lapses=row.lapses,
    )


async def states_of(
    session: AsyncSession, item_ids: list[uuid.UUID], *, user_id: uuid.UUID
) -> dict[uuid.UUID, PracticeItemState]:
    if not item_ids:
        return {}
    rows = await session.scalars(
        select(PracticeItemState).where(
            PracticeItemState.user_id == user_id, PracticeItemState.item_id.in_(item_ids)
        )
    )
    return {row.item_id: row for row in rows}


def item_out(
    item: PracticeItem,
    sources: list[ItemSourceOut],
    state: PracticeItemState | None = None,
    now: datetime | None = None,
) -> ItemOut:
    return ItemOut(
        id=item.id,
        module_id=item.module_id,
        topic_id=item.topic_id,
        kind=item.kind,
        prompt=item.prompt,
        answer=item.answer,
        key_points=item.key_points,
        origin=item.origin,
        status=item.status,
        reject_reason=item.reject_reason,
        provider=item.provider,
        model=item.model,
        generation_id=item.generation_id,
        created_at=item.created_at,
        updated_at=item.updated_at,
        sources=sources,
        pages=distinct_pages(sources),
        # Written by the AI from passages that have all gone (their material was deleted).
        sources_missing=item.provider is not None and not sources,
        memory=memory_out(state, now or clock.now()),
    )


async def items_out(
    session: AsyncSession,
    items: list[PracticeItem],
    *,
    user_id: uuid.UUID,
    now: datetime | None = None,
) -> list[ItemOut]:
    ids = [i.id for i in items]
    sources = await sources_of(session, ids, user_id=user_id)
    states = await states_of(session, ids, user_id=user_id)
    at = now or clock.now()
    return [item_out(item, sources.get(item.id, []), states.get(item.id), at) for item in items]


def _filtered(query: Select[Any], user_id: uuid.UUID, filters: ItemFilters) -> Select[Any]:
    query = query.where(PracticeItem.user_id == user_id)
    if filters.module_id is not None:
        query = query.where(PracticeItem.module_id == filters.module_id)
    if filters.topic_id is not None:
        query = query.where(PracticeItem.topic_id == filters.topic_id)
    if filters.status is not None:
        query = query.where(PracticeItem.status == filters.status)
    if filters.origin is not None:
        query = query.where(PracticeItem.origin == filters.origin)
    if filters.kind is not None:
        query = query.where(PracticeItem.kind == filters.kind)
    return query


async def list_items(
    session: AsyncSession,
    filters: ItemFilters,
    *,
    user_id: uuid.UUID,
    limit: int,
    offset: int,
) -> tuple[list[ItemOut], int]:
    """The user's items matching the filters, newest first, and how many match in all."""
    total = await session.scalar(
        _filtered(select(func.count()).select_from(PracticeItem), user_id, filters)
    )
    items = list(
        await session.scalars(
            _filtered(select(PracticeItem), user_id, filters)
            .order_by(PracticeItem.created_at.desc(), PracticeItem.id)
            .limit(limit)
            .offset(offset)
        )
    )
    return await items_out(session, items, user_id=user_id), int(total or 0)


async def _check_topic(
    session: AsyncSession, topic_id: uuid.UUID, module_id: uuid.UUID, *, user_id: uuid.UUID
) -> None:
    # (Not academics.get_topic: topics imports topic review, which imports this module.)
    topic = await session.scalar(
        select(Topic).where(Topic.id == topic_id, Topic.user_id == user_id)
    )
    if topic is None:
        raise NotFound("Topic")
    if topic.module_id != module_id:
        raise Invalid("The topic must be in the item's module")


def _check_key_points(kind: str, key_points: list[str] | None) -> None:
    if kind == "flashcard" and key_points:
        raise Invalid("A flashcard has no key points")
    if kind == "short_answer" and not key_points:
        raise Invalid("A short-answer question needs 1 to 5 key points")


@asynccontextmanager
async def _prompt_unique(
    session: AsyncSession, existing: PracticeItem | None = None
) -> AsyncIterator[None]:
    """Run a change in a SAVEPOINT: a prompt the topic already has is a ``Conflict``, and
    the rest of the session stays usable (``existing`` is reloaded)."""
    try:
        async with session.begin_nested():
            yield
            await session.flush()
    except IntegrityError as exc:
        if "uq_practice_items_topic_prompt" not in str(exc.orig):
            raise
        if existing is not None:
            await session.refresh(existing)
        raise Conflict(DUPLICATE) from exc


async def create_item(session: AsyncSession, data: ItemCreate, *, user_id: uuid.UUID) -> ItemOut:
    await get_module(session, data.module_id, user_id=user_id)
    if data.topic_id is not None:
        await _check_topic(session, data.topic_id, data.module_id, user_id=user_id)
    item = PracticeItem(
        id=uuid.uuid4(),
        user_id=user_id,
        module_id=data.module_id,
        topic_id=data.topic_id,
        kind=data.kind,
        prompt=data.prompt,
        answer=data.answer,
        key_points=data.key_points if data.kind == "short_answer" else None,
        origin="user",
        status="active",
        prompt_key=prompt_key(data.prompt),
    )
    async with _prompt_unique(session):
        session.add(item)
    await session.commit()
    await session.refresh(item)
    return item_out(item, [])


async def update_item(
    session: AsyncSession, item_id: uuid.UUID, data: ItemUpdate, *, user_id: uuid.UUID
) -> ItemOut:
    item = await get_item(session, item_id, user_id=user_id)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("topic_id") is not None:
        await _check_topic(session, changes["topic_id"], item.module_id, user_id=user_id)
    if "key_points" in changes:
        _check_key_points(item.kind, changes["key_points"])
        if item.kind == "flashcard":
            changes["key_points"] = None

    edited = any(name in changes and changes[name] != getattr(item, name) for name in TEXT_FIELDS)
    async with _prompt_unique(session, item):
        for name, value in changes.items():
            setattr(item, name, value)
        if "prompt" in changes:
            item.prompt_key = prompt_key(item.prompt)
        if edited:
            item.origin = "user"
        if "status" in changes and item.status != "rejected":
            item.reject_reason = None
    await session.commit()
    await session.refresh(item)
    [out] = await items_out(session, [item], user_id=user_id)
    return out


async def delete_item(session: AsyncSession, item_id: uuid.UUID, *, user_id: uuid.UUID) -> None:
    item = await get_item(session, item_id, user_id=user_id)
    await session.delete(item)
    await session.commit()


async def list_reviews(
    session: AsyncSession, item_id: uuid.UUID, *, user_id: uuid.UUID
) -> list[Review]:
    """The item's reviews, newest first."""
    await get_item(session, item_id, user_id=user_id)
    return list(
        await session.scalars(
            select(Review)
            .where(Review.user_id == user_id, Review.item_id == item_id)
            .order_by(Review.reviewed_at.desc(), Review.id)
        )
    )


async def move_items(
    session: AsyncSession, topic_id: uuid.UUID, target_id: uuid.UUID, *, user_id: uuid.UUID
) -> None:
    """Move a topic's items to the target (no commit). An item whose prompt the target
    already has (among items that aren't rejected) is rejected as a duplicate."""
    taken = set(
        await session.scalars(
            select(PracticeItem.prompt_key).where(
                PracticeItem.user_id == user_id,
                PracticeItem.topic_id == target_id,
                PracticeItem.status != "rejected",
            )
        )
    )
    moving = await session.scalars(
        select(PracticeItem)
        .where(PracticeItem.user_id == user_id, PracticeItem.topic_id == topic_id)
        .order_by(PracticeItem.created_at, PracticeItem.id)
    )
    for item in moving:
        if item.status != "rejected":
            if item.prompt_key in taken:
                item.status, item.reject_reason = "rejected", "duplicate"
            else:
                taken.add(item.prompt_key)
        item.topic_id = target_id
    await session.flush()
