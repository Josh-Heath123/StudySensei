"""``load_plan_data``: the planner's inputs from the database (decision 0018), against real
Postgres. Read-only and scoped by ``user_id``."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AvailabilityException, AvailabilityRule, Module, StudySession, Topic, User
from app.schemas.academics import AssessmentCreate, TopicCreate
from app.services.academics import assessments, topics
from app.services.errors import Invalid
from app.services.planning.inputs import build_plan_input, load_plan_data
from tests.academics.conftest import Rows, make_rows

SAST = ZoneInfo("Africa/Johannesburg")
# Friday 20 November 2026, 08:00 in Johannesburg.
NOW = datetime(2026, 11, 20, 8, 0, tzinfo=SAST)


async def every_evening(session: AsyncSession, user: User, start: int = 1080) -> None:
    """18:00-20:00 (or from ``start``, for two hours) on every weekday."""
    for weekday in range(7):
        session.add(
            AvailabilityRule(
                user_id=user.id, weekday=weekday, start_minute=start, end_minute=start + 120
            )
        )
    await session.commit()


async def due_in(session: AsyncSession, rows: Rows, days: float, **fields: object) -> None:
    """Give the row's assessment a deadline ``days`` after NOW (and any other fields)."""
    rows.assessment.due_at = NOW + timedelta(days=days)
    for name, value in fields.items():
        setattr(rows.assessment, name, value)
    await session.commit()


async def studied(
    session: AsyncSession, user: User, module: Module, topic: Topic, seconds: float
) -> None:
    """An ended session on ``topic`` with ``seconds`` of active time."""
    started = NOW - timedelta(days=2)
    session.add(
        StudySession(
            user_id=user.id,
            module_id=module.id,
            topic_id=topic.id,
            state="ended",
            started_at=started,
            ended_at=started + timedelta(seconds=seconds),
            last_event_at=started + timedelta(seconds=seconds),
            active_seconds=seconds,
            break_seconds=0,
        )
    )
    await session.commit()


async def test_another_users_sessions_assessments_and_topics_never_count(
    session: AsyncSession, user_a: User, user_b: User
) -> None:
    alice = await make_rows(session, user_a)
    bob = await make_rows(session, user_b)
    await due_in(session, alice, 5, weight=Decimal("30"))
    await due_in(session, bob, 3)
    await every_evening(session, user_a)
    await every_evening(session, user_b, start=6 * 60)  # his mornings, not her time
    await studied(session, user_b, bob.module, bob.topic, 7200)

    data = await load_plan_data(session, user_id=user_a.id, now=NOW, days=7)
    request = data.input

    assert [a.id for a in request.assessments] == [alice.assessment.id]
    assert request.assessments[0].weight == 30.0
    assert request.assessments[0].topic_ids == (alice.topic.id,)
    assert [t.id for t in request.topics] == [alice.topic.id]
    # Her own 50-minute session from make_rows; his two hours don't count.
    assert request.studied_minutes == {alice.topic.id: 50}
    assert data.facts.topics[alice.topic.id].sessions == 1
    assert set(data.facts.modules) == {alice.module.id}
    # Her evenings only: every interval starts at 18:00 local.
    assert request.free
    assert {i.start.astimezone(SAST).hour for i in request.free} == {18}
    assert request.daily_cap_minutes == 180
    assert request.timezone == SAST


async def test_past_completed_and_cancelled_assessments_are_left_out(
    session: AsyncSession, user_a: User
) -> None:
    rows = await make_rows(session, user_a)
    await due_in(session, rows, -1)  # yesterday
    uid = user_a.id
    for title, status, days in [
        ("Done", "completed", 3),
        ("Off", "cancelled", 3),
        ("Next", "upcoming", 3),
        ("Exam", "upcoming", 40),  # after a 28-day window
    ]:
        await assessments.create_assessment(
            session,
            rows.module.id,
            AssessmentCreate(
                title=title,
                kind="exam",
                status=status,
                due_at=NOW + timedelta(days=days),
                topic_ids=[rows.topic.id],
            ),
            user_id=uid,
        )

    data = await load_plan_data(session, user_id=uid, now=NOW, days=28)

    titles = {data.facts.assessments[a.id].title for a in data.input.assessments}
    assert titles == {"Next"}
    # The exam is known, but listed as later rather than planned.
    assert [data.facts.assessments[a].title for a in data.facts.later] == ["Exam"]


async def test_an_exception_empties_its_day(session: AsyncSession, user_a: User) -> None:
    rows = await make_rows(session, user_a)
    await due_in(session, rows, 10)
    await every_evening(session, user_a)
    off = date(2026, 11, 23)
    session.add(AvailabilityException(user_id=user_a.id, date=off, unavailable=True, windows=[]))
    await session.commit()

    request = await build_plan_input(session, user_id=user_a.id, now=NOW, days=7)

    days = {i.start.astimezone(SAST).date() for i in request.free}
    assert off not in days
    assert days == {NOW.date() + timedelta(days=n) for n in range(7)} - {off}


async def test_a_session_on_a_subtopic_counts_for_that_subtopic_only(
    session: AsyncSession, user_a: User
) -> None:
    rows = await make_rows(session, user_a)
    child = await topics.create_topic(
        session,
        rows.module.id,
        TopicCreate(name="Service discovery", parent_id=rows.topic.id),
        user_id=user_a.id,
    )
    await assessments.set_assessment_topics(
        session, rows.assessment.id, {rows.topic.id, child.id}, user_id=user_a.id
    )
    await due_in(session, rows, 5)
    await studied(session, user_a, rows.module, child, 30 * 60 + 59)  # floors to 30

    request = await build_plan_input(session, user_id=user_a.id, now=NOW, days=7)

    # The parent keeps only its own session (50 min from make_rows).
    assert request.studied_minutes == {rows.topic.id: 50, child.id: 30}


async def test_workload_is_yours_else_estimated_else_none(
    session: AsyncSession, user_a: User
) -> None:
    rows = await make_rows(session, user_a)
    other = await topics.create_topic(
        session, rows.module.id, TopicCreate(name="Sagas"), user_id=user_a.id
    )
    await assessments.set_assessment_topics(
        session, rows.assessment.id, {rows.topic.id, other.id}, user_id=user_a.id
    )
    rows.topic.estimated_minutes = 90
    rows.topic.confidence = 2
    await due_in(session, rows, 5)

    data = await load_plan_data(session, user_id=user_a.id, now=NOW, days=7)

    by_id = {t.id: t for t in data.input.topics}
    assert (by_id[rows.topic.id].workload_minutes, by_id[rows.topic.id].confidence) == (90, 2)
    assert data.facts.topics[rows.topic.id].workload_source == "yours"
    assert by_id[other.id].workload_minutes is None
    assert data.facts.topics[other.id].workload_source == "none"


@pytest.mark.parametrize("days", [0, 63])
async def test_the_window_is_1_to_62_days(session: AsyncSession, user_a: User, days: int) -> None:
    with pytest.raises(Invalid):
        await load_plan_data(session, user_id=user_a.id, now=datetime.now(UTC), days=days)
