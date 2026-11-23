"""Loading mastery's inputs and computing it on read (ADR 0027). Read-only; every query is
scoped by ``user_id``.

Nothing is stored: the review log, the quiz answers and the ratings can recompute mastery as of
any past time (``at``), so a trend (Phase 8) loses nothing. One module at a time: its topics,
the items in it (never rejected ones; an item without a topic belongs to no subtree), their
reviews up to ``at``, the answered Quiz me questions of its conversations that have a topic, and
the session reflection ratings and starting confidences. Each item is summarised once and shared
by every topic whose subtree holds it.

Sources:

- recall: ``reviews.state_after`` of each active item's latest scheduled review up to ``at``
  (the same state ``practice_item_states`` holds for ``at`` = now);
- attempts: ``reviews`` (grade, reviewed_at) and ``messages.quiz`` / ``quiz_answers``, graded by
  ``tutor.quiz.grade`` and dated by the message's ``updated_at`` (when the picks were saved);
- the prior: ``session_topic_ratings`` (dated by the session's reflection, else its end, else its
  start) and ``topics.confidence``.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Conversation,
    Message,
    PracticeItem,
    Review,
    SessionTopicRating,
    StudySession,
    Topic,
    User,
)
from app.schemas.tutor import Quiz
from app.services.academics.modules import get_module
from app.services.academics.topics import get_topic
from app.services.errors import NotFound
from app.services.mastery.formula import (
    Attempt,
    ItemLog,
    ItemSummary,
    Mastery,
    QuizAnswer,
    ReviewLog,
    quiz_attempt,
    resolve_prior,
    summarise_item,
    topic_mastery,
)
from app.services.planning.subtree import make_tree, subtree
from app.services.practice.scheduling import MemoryState
from app.services.tutor.quiz import grade


@dataclass(frozen=True)
class TopicMastery:
    topic_id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    mastery: Mastery


async def _timezone(session: AsyncSession, user_id: uuid.UUID) -> str:
    found = await session.scalar(select(User.timezone).where(User.id == user_id))
    if found is None:
        raise NotFound("User")
    return found


async def _item_logs(
    session: AsyncSession, module_id: uuid.UUID, *, user_id: uuid.UUID, at: datetime
) -> dict[uuid.UUID, tuple[uuid.UUID, ItemLog]]:
    """Item id → (its topic, its log), for the module's items that have a topic."""
    items = (
        await session.execute(
            select(PracticeItem.id, PracticeItem.topic_id, PracticeItem.status).where(
                PracticeItem.user_id == user_id,
                PracticeItem.module_id == module_id,
                PracticeItem.status != "rejected",
                PracticeItem.topic_id.is_not(None),
            )
        )
    ).all()
    reviews: dict[uuid.UUID, list[ReviewLog]] = defaultdict(list)
    rows = await session.execute(
        select(Review.item_id, Review.reviewed_at, Review.grade, Review.state_after)
        .join(
            PracticeItem,
            (PracticeItem.id == Review.item_id) & (PracticeItem.user_id == Review.user_id),
        )
        .where(
            Review.user_id == user_id,
            PracticeItem.module_id == module_id,
            Review.reviewed_at <= at,
        )
    )
    for item_id, reviewed_at, grade_, state_after in rows:
        state = MemoryState.from_snapshot(state_after) if state_after is not None else None
        reviews[item_id].append(ReviewLog(reviewed_at, grade_, state))
    return {
        item_id: (topic_id, ItemLog(item_id, status == "active", tuple(reviews[item_id])))
        for item_id, topic_id, status in items
        if topic_id is not None
    }


async def _quiz_answers(
    session: AsyncSession, module_id: uuid.UUID, *, user_id: uuid.UUID, at: datetime
) -> dict[uuid.UUID, list[QuizAnswer]]:
    """Topic id → its conversations' answered quiz questions, graded by code."""
    rows = await session.execute(
        select(Conversation.topic_id, Message.updated_at, Message.quiz, Message.quiz_answers)
        .join(
            Conversation,
            (Conversation.id == Message.conversation_id)
            & (Conversation.user_id == Message.user_id),
        )
        .where(
            Message.user_id == user_id,
            Conversation.module_id == module_id,
            Conversation.topic_id.is_not(None),
            Message.quiz.is_not(None),
            Message.quiz_answers.is_not(None),
            Message.updated_at <= at,
        )
    )
    out: dict[uuid.UUID, list[QuizAnswer]] = defaultdict(list)
    for topic_id, answered_at, quiz, answers in rows:
        for right in grade(Quiz.model_validate(quiz), answers):
            if right is not None:
                out[topic_id].append(QuizAnswer(answered_at, right))
    return out


async def _latest_session_ratings(
    session: AsyncSession, module_id: uuid.UUID, *, user_id: uuid.UUID, at: datetime
) -> dict[uuid.UUID, int]:
    rated_at = func.coalesce(
        StudySession.reflected_at, StudySession.ended_at, StudySession.started_at
    )
    rows = await session.execute(
        select(SessionTopicRating.topic_id, SessionTopicRating.confidence)
        .join(
            StudySession,
            (StudySession.id == SessionTopicRating.session_id)
            & (StudySession.module_id == SessionTopicRating.module_id),
        )
        .where(
            StudySession.user_id == user_id,
            SessionTopicRating.module_id == module_id,
            rated_at <= at,
        )
        # The latest wins: later rows overwrite earlier ones below.
        .order_by(rated_at, SessionTopicRating.session_id)
    )
    return {topic_id: confidence for topic_id, confidence in rows}


async def module_mastery(
    session: AsyncSession, module_id: uuid.UUID, *, user_id: uuid.UUID, at: datetime
) -> list[TopicMastery]:
    """Every topic of the module, in tree order (a parent before its children), with its
    mastery as of ``at``. ``NotFound`` for another user's module."""
    await get_module(session, module_id, user_id=user_id)
    tz = ZoneInfo(await _timezone(session, user_id))
    topics = (
        await session.execute(
            select(Topic.id, Topic.parent_id, Topic.name, Topic.confidence)
            .where(Topic.user_id == user_id, Topic.module_id == module_id)
            .order_by(Topic.position, Topic.name)
        )
    ).all()
    tree = make_tree([(t.id, t.parent_id) for t in topics])
    starting = {t.id: t.confidence for t in topics}
    latest = await _latest_session_ratings(session, module_id, user_id=user_id, at=at)
    logs = await _item_logs(session, module_id, user_id=user_id, at=at)
    quiz = await _quiz_answers(session, module_id, user_id=user_id, at=at)

    by_topic: dict[uuid.UUID, list[ItemSummary]] = defaultdict(list)
    for topic_id, log in logs.values():
        by_topic[topic_id].append(summarise_item(log, at, tz))
    quiz_by_topic: dict[uuid.UUID, list[Attempt]] = {
        topic_id: [quiz_attempt(a, tz) for a in answers] for topic_id, answers in quiz.items()
    }

    out = []
    for t in sorted(topics, key=lambda t: tree.order[t.id]):
        members = subtree(tree, t.id)
        result = topic_mastery(
            [s for m in members for s in by_topic.get(m, ())],
            [a for m in members for a in quiz_by_topic.get(m, ())],
            resolve_prior(tree, t.id, latest, starting),
            at,
        )
        out.append(TopicMastery(t.id, t.parent_id, t.name, result))
    return out


async def one_topic_mastery(
    session: AsyncSession, topic_id: uuid.UUID, *, user_id: uuid.UUID, at: datetime
) -> TopicMastery:
    topic = await get_topic(session, topic_id, user_id=user_id)
    found = await module_mastery(session, topic.module_id, user_id=user_id, at=at)
    return next(t for t in found if t.topic_id == topic_id)
