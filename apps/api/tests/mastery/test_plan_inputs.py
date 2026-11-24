"""``load_plan_data`` with mastery (ADR 0031): each unit's mastery over its subtree at ``now``,
only when estimated; ``use_mastery=False`` (the preview's ``--no-mastery``) ignores it."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Assessment, AvailabilityRule, User
from app.schemas.practice import ItemCreate, ReviewIn
from app.services.academics import assessments
from app.services.mastery.load import mastery_by_topic, module_mastery
from app.services.planning.inputs import load_plan_data
from app.services.practice import items
from app.services.practice.reviewing import review_item
from tests.practice.conftest import Practice

T0 = datetime(2026, 11, 2, 6, 0, tzinfo=UTC)
NOW = T0 + timedelta(days=1)


async def practise(
    session: AsyncSession, practice: Practice, topic: uuid.UUID, grades: list[int]
) -> None:
    for n, grade in enumerate(grades):
        created = await items.create_item(
            session,
            ItemCreate(
                module_id=practice.module_id,
                topic_id=topic,
                kind="flashcard",
                prompt=f"Idea {topic.hex[:6]} number {n}?",
                answer="An answer.",
            ),
            user_id=practice.user_id,
        )
        review = ReviewIn(grade=grade)
        at = T0 + timedelta(minutes=n)
        await review_item(session, created.id, review, user_id=practice.user_id, now=at)


async def plan_for_both(session: AsyncSession, practice: Practice, user: User) -> None:
    """Every evening free, and the fixture's test due in 10 days on the chapter and Ciphers."""
    for weekday in range(7):
        session.add(
            AvailabilityRule(user_id=user.id, weekday=weekday, start_minute=1080, end_minute=1260)
        )
    test = await session.get(Assessment, (await first_assessment(session, practice)))
    assert test is not None
    test.due_at = NOW + timedelta(days=10)
    await session.commit()
    await assessments.set_assessment_topics(
        session, test.id, {practice.chapter, practice.other}, user_id=user.id
    )
    await session.commit()


async def first_assessment(session: AsyncSession, practice: Practice) -> uuid.UUID:
    found = await session.scalar(
        select(Assessment.id).where(
            Assessment.user_id == practice.user_id, Assessment.module_id == practice.module_id
        )
    )
    assert found is not None
    return found


async def test_each_unit_gets_its_subtrees_estimated_mastery(
    session: AsyncSession, practice: Practice, user_a: User
) -> None:
    await plan_for_both(session, practice, user_a)
    # The chapter's practice is on its subtopic (the unit covers its subtree): 3 Agains.
    await practise(session, practice, practice.sub, [1, 1, 1])
    # Ciphers: 2 attempts, not enough for an estimate.
    await practise(session, practice, practice.other, [3, 3])

    data = await load_plan_data(session, user_id=user_a.id, now=NOW)
    by_id = {t.id: t for t in data.input.topics}
    expected = {
        t.topic_id: t.mastery
        for t in await module_mastery(session, practice.module_id, user_id=user_a.id, at=NOW)
    }
    chapter = expected[practice.chapter]
    assert chapter.status == "estimated" and chapter.value < 0.5
    assert by_id[practice.chapter].mastery == chapter.value
    assert data.facts.topics[practice.chapter].mastery == chapter.value
    assert data.facts.topics[practice.chapter].mastery_attempts == 3
    # Not enough practice: no mastery, so the rating decides.
    assert expected[practice.other].status == "not_enough"
    assert by_id[practice.other].mastery is None
    assert data.facts.topics[practice.other].mastery_attempts == 0

    ignored = await load_plan_data(session, user_id=user_a.id, now=NOW, use_mastery=False)
    assert all(t.mastery is None for t in ignored.input.topics)
    assert all(f.mastery is None for f in ignored.facts.topics.values())


async def test_one_call_covers_every_module(
    session: AsyncSession, practice: Practice, user_a: User
) -> None:
    found = await mastery_by_topic(
        session, [practice.module_id, practice.module_id], user_id=user_a.id, at=NOW
    )
    assert set(found) == {practice.chapter, practice.sub, practice.other}
