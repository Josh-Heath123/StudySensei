"""Reviewing a practice item with FSRS (ADR 0026). Every query is scoped by ``user_id``.

A review happens under a row lock on the item (``SELECT … FOR UPDATE``: the item always has a
row, its state may not yet), so two reviews of one item at once are serialised: the second
reads the state the first wrote. In one transaction it computes the new state with
``scheduling.schedule`` at the given time and the user's desired retention, writes the
review (with the state before and after, the days scheduled, the retention and the library
version) and upserts the item's state. FSRS is ordinary code: no AI touches a schedule.

Only active items are reviewed; a suspended or rejected one is a ``Conflict``. The student
always chooses the grade. An AI marking they saw (ADR 0029) is stored with the review, after
checking it's for the item's key points as they are now.

Each review also queues a re-plan (trigger "practice", ADR 0031) 15 minutes later, in the same
transaction: mastery moves the plan, and the queue keeps one job at its earliest time, so a
sitting of reviews yields one re-plan after it.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.queue import enqueue_replan
from app.models import PracticeItem, PracticeItemState, Review, User
from app.schemas.practice import PreviewOption, PreviewOut, ReviewIn
from app.services.errors import Conflict, Invalid, NotFound
from app.services.practice.items import get_item, memory_state
from app.services.practice.scheduling import (
    FSRS_VERSION,
    MemoryState,
    SchedulingSettings,
    interval_label,
    schedule,
)

RESTORE = "Restore it before reviewing."
MARKING_MISMATCH = "That AI marking isn't for this question as it is now. Check it again."
GRADE_NAMES = {1: "again", 2: "hard", 3: "good", 4: "easy"}
# A review's re-plan waits this long, so a sitting of reviews leads to one re-plan.
REPLAN_AFTER = timedelta(minutes=15)


@dataclass(frozen=True)
class Reviewed:
    review: Review
    state: MemoryState
    scheduled_days: int


async def user_settings(session: AsyncSession, *, user_id: uuid.UUID) -> SchedulingSettings:
    retention = await session.scalar(
        select(User.practice_desired_retention).where(User.id == user_id)
    )
    if retention is None:
        raise NotFound("User")
    return SchedulingSettings(desired_retention=retention)


async def current_state(
    session: AsyncSession, item_id: uuid.UUID, *, user_id: uuid.UUID, lock: bool = False
) -> MemoryState | None:
    query = select(PracticeItemState).where(
        PracticeItemState.item_id == item_id, PracticeItemState.user_id == user_id
    )
    row = await session.scalar(query.with_for_update() if lock else query)
    return memory_state(row) if row is not None else None


async def review_item(
    session: AsyncSession,
    item_id: uuid.UUID,
    data: ReviewIn,
    *,
    user_id: uuid.UUID,
    now: datetime,
) -> Reviewed:
    item = await session.scalar(
        select(PracticeItem)
        .where(PracticeItem.id == item_id, PracticeItem.user_id == user_id)
        .with_for_update()
    )
    if item is None:
        raise NotFound("Practice item")
    if item.status != "active":
        raise Conflict(RESTORE)
    if data.ai_marking is not None and [c.key_point for c in data.ai_marking.coverage] != list(
        item.key_points or []
    ):
        # A flashcard, or key points edited since the marking.
        raise Invalid(MARKING_MISMATCH)
    settings = await user_settings(session, user_id=user_id)
    before = await current_state(session, item.id, user_id=user_id, lock=True)
    after, days = schedule(before, data.grade, now, settings)
    review = Review(
        user_id=user_id,
        item_id=item.id,
        reviewed_at=after.last_review_at,
        grade=data.grade,
        marked_by=data.marked_by,
        ai_marking=data.ai_marking.model_dump(mode="json") if data.ai_marking else None,
        duration_ms=data.duration_ms,
        answer_text=data.answer_text,
        state_before=before.snapshot() if before is not None else None,
        state_after=after.snapshot(),
        scheduled_days=days,
        desired_retention=settings.desired_retention,
        fsrs_version=FSRS_VERSION,
    )
    session.add(review)
    values = {
        "state": after.state,
        "step": after.step,
        "stability": after.stability,
        "difficulty": after.difficulty,
        "due": after.due,
        "last_review_at": after.last_review_at,
        "reps": after.reps,
        "lapses": after.lapses,
    }
    await session.execute(
        insert(PracticeItemState)
        .values(item_id=item.id, user_id=user_id, **values)
        .on_conflict_do_update(index_elements=["item_id"], set_=values)
    )
    await enqueue_replan(session, user_id=user_id, trigger="practice", run_after=now + REPLAN_AFTER)
    await session.commit()
    await session.refresh(review)
    return Reviewed(review, after, days)


async def preview(
    session: AsyncSession, item_id: uuid.UUID, *, user_id: uuid.UUID, now: datetime
) -> PreviewOut:
    """What each grade would schedule, now: for the buttons. Nothing is written."""
    item = await get_item(session, item_id, user_id=user_id)
    settings = await user_settings(session, user_id=user_id)
    before = await current_state(session, item.id, user_id=user_id)
    options = []
    for grade, name in GRADE_NAMES.items():
        after, _ = schedule(before, grade, now, settings)
        options.append(
            PreviewOption(
                grade=grade,
                name=name,
                due=after.due,
                interval=interval_label(after.due - after.last_review_at),
            )
        )
    return PreviewOut(at=now, options=options)
