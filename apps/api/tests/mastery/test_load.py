"""Mastery on read (ADR 0027): the loader against real Postgres, the API, and the timing of a
module with 60 topics and 600 items."""

import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
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
from app.schemas.practice import ItemCreate, ReviewIn
from app.services.mastery.formula import ItemLog, Prior, QuizAnswer, ReviewLog, mastery
from app.services.mastery.load import module_mastery, one_topic_mastery
from app.services.practice import items
from app.services.practice.filter import prompt_key
from app.services.practice.reviewing import review_item
from app.services.practice.scheduling import MemoryState, SchedulingSettings, schedule
from tests.api.conftest import ClientFactory
from tests.practice.conftest import Practice

T0 = datetime(2026, 11, 2, 6, 0, tzinfo=UTC)
# After the fixture's session, reflected on the real clock.
AT = datetime.now(UTC) + timedelta(hours=1)


@pytest.fixture
async def api(client_as: ClientFactory, user_a: User) -> AsyncIterator[AsyncClient]:
    async with client_as(user_a) as client:
        yield client


async def card(
    session: AsyncSession, practice: Practice, topic: uuid.UUID | None, n: int
) -> uuid.UUID:
    out = await items.create_item(
        session,
        ItemCreate(
            module_id=practice.module_id,
            topic_id=topic,
            kind="flashcard",
            prompt=f"Question {n}?",
            answer="An answer.",
        ),
        user_id=practice.user_id,
    )
    return out.id


async def review(
    session: AsyncSession, practice: Practice, item_id: uuid.UUID, grade: int, at: datetime
) -> None:
    await review_item(session, item_id, ReviewIn(grade=grade), user_id=practice.user_id, now=at)


async def quiz(
    session: AsyncSession,
    practice: Practice,
    topic: uuid.UUID | None,
    answers: list[int | None],
    at: datetime,
) -> None:
    """A Quiz me message whose right option is always 0."""
    conversation = Conversation(
        user_id=practice.user_id, module_id=practice.module_id, topic_id=topic
    )
    session.add(conversation)
    await session.flush()
    question = {
        "prompt": "Which?",
        "options": ["a", "b", "c", "d"],
        "correct": 0,
        "explanation": "Because [S1].",
        "sources": ["S1"],
    }
    session.add(
        Message(
            user_id=practice.user_id,
            conversation_id=conversation.id,
            position=0,
            role="assistant",
            mode="quiz",
            text="Quiz.",
            status="complete",
            quiz={"questions": [question] * len(answers)},
            quiz_answers=answers,
            updated_at=at,
        )
    )
    await session.commit()


def by_name(found: list[Any]) -> dict[str, Any]:
    return {t.name: t for t in found}


async def test_a_chapter_holds_its_subtopics_practice_and_the_api_says_so(
    session: AsyncSession, practice: Practice, api: AsyncClient
) -> None:
    on_chapter = await card(session, practice, practice.chapter, 1)
    on_sub = await card(session, practice, practice.sub, 2)
    await card(session, practice, practice.sub, 3)  # never reviewed
    await review(session, practice, on_chapter, 3, T0)
    await review(session, practice, on_chapter, 3, T0 + timedelta(minutes=10))  # same day
    await review(session, practice, on_sub, 1, T0 + timedelta(days=1))
    await quiz(session, practice, practice.sub, [0, 1, None], T0 + timedelta(days=2))
    await quiz(session, practice, practice.other, [0], T0 + timedelta(days=2))

    found = await module_mastery(session, practice.module_id, user_id=practice.user_id, at=AT)
    # Tree order: the chapter, its subtopic, then the other topic.
    assert [t.topic_id for t in found] == [practice.chapter, practice.sub, practice.other]
    chapter, sub, other = (t.mastery for t in found)
    assert (chapter.samples.attempts, chapter.samples.reviews) == (4, 3)
    assert (chapter.samples.items_reviewed, chapter.samples.items_active) == (2, 3)
    assert (chapter.samples.quiz_answers, chapter.samples.days_spanned) == (2, 3)
    # The fixture's ended session rated the chapter 3; nothing rates the subtopic.
    assert (chapter.samples.rating_source, chapter.components.prior) == ("session", 0.5)
    assert sub.samples.rating_source == "none"
    assert (sub.samples.attempts, sub.samples.items_active) == (3, 2)
    assert (other.samples.attempts, other.components.recall) == (1, None)
    assert other.status == "not_enough"

    # The loader gives the pure formula exactly these inputs.
    chapter_logs = []
    for item_id in (on_chapter, on_sub):
        listed = await items.list_reviews(session, item_id, user_id=practice.user_id)
        chapter_logs.append(
            ItemLog(
                item_id,
                True,
                tuple(
                    ReviewLog(
                        r.reviewed_at,
                        r.grade,
                        MemoryState.from_snapshot(r.state_after) if r.state_after else None,
                    )
                    for r in listed
                ),
            )
        )
    answers = [QuizAnswer(T0 + timedelta(days=2), True), QuizAnswer(T0 + timedelta(days=2), False)]
    expected = mastery(chapter_logs, answers, Prior(3, "session"), AT, "UTC")
    assert expected.value == chapter.value
    assert expected.basis == chapter.basis

    body = (await api.get(f"/modules/{practice.module_id}/mastery")).json()
    assert [t["name"] for t in body["topics"]] == [t.name for t in found]
    first = body["topics"][0]
    assert (first["label"], first["status"]) == ("estimated", "estimated")
    assert set(first["components"]) == {"recall", "accuracy", "prior", "weight", "recall_weight"}
    one = (await api.get(f"/topics/{practice.sub}/mastery")).json()
    assert one["topic_id"] == str(practice.sub) and one["parent_id"] == str(practice.chapter)
    assert (await api.get(f"/topics/{uuid.uuid4()}/mastery")).status_code == 404
    assert (await api.get(f"/modules/{uuid.uuid4()}/mastery")).status_code == 404


async def test_rejected_and_topicless_items_and_later_events_are_left_out(
    session: AsyncSession, practice: Practice
) -> None:
    kept = await card(session, practice, practice.other, 1)
    rejected = await card(session, practice, practice.other, 2)
    loose = await card(session, practice, None, 3)
    for item_id in (kept, rejected, loose):
        await review(session, practice, item_id, 3, T0)
    await review(session, practice, kept, 1, AT + timedelta(days=1))  # after ``at``
    await session.execute(
        update(PracticeItem)
        .where(PracticeItem.id == rejected)
        .values(status="rejected", reject_reason="wrong")
    )
    await session.commit()
    other = (
        await one_topic_mastery(session, practice.other, user_id=practice.user_id, at=AT)
    ).mastery
    assert (other.samples.items_active, other.samples.reviews, other.samples.attempts) == (1, 1, 1)


async def test_the_latest_session_rating_wins_and_a_starting_one_stands_in(
    session: AsyncSession, practice: Practice
) -> None:
    # The fixture's session rated the chapter 3; date it a day before T0.
    first = await session.scalar(
        select(StudySession.id).where(StudySession.user_id == practice.user_id)
    )
    # A later session rated the chapter 5.
    later = StudySession(
        user_id=practice.user_id,
        module_id=practice.module_id,
        topic_id=practice.chapter,
        state="ended",
        started_at=T0,
        ended_at=T0 + timedelta(hours=1),
        last_event_at=T0 + timedelta(hours=1),
        active_seconds=3600,
        break_seconds=0,
        reflected_at=T0 + timedelta(hours=1),
    )
    session.add(later)
    await session.flush()
    session.add(
        SessionTopicRating(
            session_id=later.id,
            topic_id=practice.chapter,
            module_id=practice.module_id,
            confidence=5,
        )
    )
    await session.execute(
        update(StudySession)
        .where(StudySession.id == first)
        .values(reflected_at=T0 - timedelta(days=1))
    )
    await session.execute(update(Topic).where(Topic.id == practice.sub).values(confidence=2))
    await session.commit()

    found = by_name(
        await module_mastery(session, practice.module_id, user_id=practice.user_id, at=AT)
    )
    chapter = found["Microservices"].mastery
    assert (chapter.components.prior, chapter.samples.rating_source) == (1.0, "session")
    assert found["Firewall types"].mastery.samples.rating_source == "starting"
    # Before the later session, the earlier rating (3) stands.
    earlier = by_name(
        await module_mastery(
            session, practice.module_id, user_id=practice.user_id, at=T0 - timedelta(hours=1)
        )
    )
    assert earlier["Microservices"].mastery.components.prior == 0.5


# --- Timing ---------------------------------------------------------------------------


async def test_a_module_with_60_topics_and_600_items_computes_in_under_200_ms(
    session: AsyncSession, practice: Practice
) -> None:
    """60 topics (the fixture's 3, six chapters and 51 subtopics), ten items each, three
    reviews per item on three days (1,800), and a three-question quiz per chapter."""
    uid, module_id = practice.user_id, practice.module_id
    topics: list[uuid.UUID] = []
    chapters: list[uuid.UUID] = []
    for c in range(6):
        chapter = Topic(user_id=uid, module_id=module_id, name=f"Chapter {c}", position=10 + c)
        session.add(chapter)
        await session.flush()
        topics.append(chapter.id)
        chapters.append(chapter.id)
        for s in range(9 if c else 6):  # 6 chapters + 51 subtopics + the fixture's 3 = 60
            sub = Topic(
                user_id=uid, module_id=module_id, parent_id=chapter.id, name=f"{c}.{s}", position=s
            )
            session.add(sub)
            await session.flush()
            topics.append(sub.id)
    topics += [practice.chapter, practice.sub, practice.other]
    assert len(topics) == 60

    settings = SchedulingSettings()
    rows_items, rows_reviews = [], []
    for n in range(600):
        item_id = uuid.uuid4()
        prompt = f"Timed question {n}?"
        rows_items.append(
            PracticeItem(
                id=item_id,
                user_id=uid,
                module_id=module_id,
                topic_id=topics[n % 60],
                kind="flashcard",
                prompt=prompt,
                answer="An answer.",
                origin="user",
                prompt_key=prompt_key(prompt),
            )
        )
        state: MemoryState | None = None
        for day, grade in ((0, 3), (2, 1 + n % 4), (5, 3)):
            at = T0 + timedelta(days=day, minutes=n % 50)
            before = state
            state, days = schedule(state, grade, at, settings)
            rows_reviews.append(
                Review(
                    user_id=uid,
                    item_id=item_id,
                    reviewed_at=at,
                    grade=grade,
                    marked_by="self",
                    state_before=before.snapshot() if before else None,
                    state_after=state.snapshot(),
                    scheduled_days=days,
                    desired_retention=0.9,
                )
            )
    session.add_all(rows_items)
    await session.flush()
    session.add_all(rows_reviews)
    await session.commit()
    for chapter_id in chapters:
        await quiz(session, practice, chapter_id, [0, 1, 0], T0 + timedelta(days=4))

    at = T0 + timedelta(days=8)
    await module_mastery(session, module_id, user_id=uid, at=at)  # warm up
    timings = []
    for _ in range(3):
        started = time.perf_counter()
        found = await module_mastery(session, module_id, user_id=uid, at=at)
        timings.append(time.perf_counter() - started)
    print(f"module mastery, 60 topics and 600 items: {[round(t * 1000) for t in timings]} ms")
    assert len(found) == 60
    assert sum(t.mastery.samples.reviews for t in found if t.parent_id is None) >= 1800
    assert min(timings) < 0.200
