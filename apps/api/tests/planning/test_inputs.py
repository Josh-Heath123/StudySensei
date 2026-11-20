"""``load_plan_data``: the planner's inputs from the database (decision 0018), against real
Postgres. Read-only and scoped by ``user_id``."""

import hashlib
import itertools
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AvailabilityException,
    AvailabilityRule,
    Chunk,
    ChunkTopic,
    Material,
    MaterialPage,
    Module,
    StudySession,
    Topic,
    User,
)
from app.models.materials import EMBEDDING_DIMENSIONS
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


# --- units are subtrees (decision 0019) ----------------------------------------------------


async def material(session: AsyncSession, rows: Rows, kind: str, pages: int) -> Material:
    """A ready material of ``kind`` with ``pages`` pages (no chunks yet)."""
    found = Material(
        user_id=rows.user.id,
        module_id=rows.module.id,
        kind=kind,
        title=kind,
        original_filename=f"{kind}.pdf",
        content_type="application/pdf",
        size_bytes=10,
        sha256=hashlib.sha256(f"{rows.user.id}{kind}".encode()).hexdigest(),
        status="ready",
        allow_ai=False,
    )
    session.add(found)
    await session.flush()
    for number in range(1, pages + 1):
        session.add(
            MaterialPage(
                user_id=rows.user.id,
                material_id=found.id,
                page_number=number,
                text="Text",
                char_count=4,
                is_scanned=False,
            )
        )
    await session.commit()
    return found


_POSITIONS = itertools.count()


async def link(session: AsyncSession, rows: Rows, page: tuple[Material, int], *on: Topic) -> None:
    """A chunk on ``page``, linked to each topic in ``on``."""
    found, number = page
    chunk = Chunk(
        user_id=rows.user.id,
        module_id=rows.module.id,
        material_id=found.id,
        page_number=number,
        position=next(_POSITIONS),
        text="Text",
        token_count=1,
        embedding=[0.0] * EMBEDDING_DIMENSIONS,
    )
    session.add(chunk)
    await session.flush()
    for topic in on:
        session.add(
            ChunkTopic(
                chunk_id=chunk.id,
                topic_id=topic.id,
                module_id=rows.module.id,
                method="pages",
                score=1.0,
            )
        )
    await session.commit()


async def child_of(session: AsyncSession, rows: Rows, parent: Topic, name: str) -> Topic:
    return await topics.create_topic(
        session, rows.module.id, TopicCreate(name=name, parent_id=parent.id), user_id=rows.user.id
    )


async def tick(session: AsyncSession, rows: Rows, *ticked: Topic) -> None:
    await assessments.set_assessment_topics(
        session, rows.assessment.id, {t.id for t in ticked}, user_id=rows.user.id
    )
    await due_in(session, rows, 5)


async def test_a_page_linked_to_a_parent_and_a_child_counts_once(
    session: AsyncSession, user_a: User
) -> None:
    rows = await make_rows(session, user_a)
    chapter, child = rows.topic, await child_of(session, rows, rows.topic, "Sagas")
    slides = await material(session, rows, "slides", 3)
    notes = await material(session, rows, "notes", 2)
    await link(session, rows, (slides, 1), chapter, child)  # both: counted once
    await link(session, rows, (slides, 2), child)
    await link(session, rows, (slides, 3), chapter)
    await link(session, rows, (notes, 1), child)
    await link(session, rows, (notes, 1), chapter)  # another chunk on the same page
    await tick(session, rows, chapter)

    data = await load_plan_data(session, user_id=user_a.id, now=NOW, days=7)

    facts = data.facts.topics[chapter.id]
    assert (facts.slide_pages, facts.text_pages, facts.subtopics) == (3, 1, 1)
    # 3 slides at 3 min and 1 page of text at 6 min: 15 min.
    assert [(t.id, t.workload_minutes) for t in data.input.topics] == [(chapter.id, 15)]


async def test_a_ticked_child_under_a_ticked_parent_is_absorbed(
    session: AsyncSession, user_a: User
) -> None:
    rows = await make_rows(session, user_a)
    child = await child_of(session, rows, rows.topic, "Sagas")
    await tick(session, rows, rows.topic, child)

    request = await build_plan_input(session, user_id=user_a.id, now=NOW, days=7)

    assert request.assessments[0].topic_ids == (rows.topic.id,)
    assert [t.id for t in request.topics] == [rows.topic.id]


async def test_a_child_ticked_alone_is_its_own_unit(session: AsyncSession, user_a: User) -> None:
    rows = await make_rows(session, user_a)
    child = await child_of(session, rows, rows.topic, "Sagas")
    slides = await material(session, rows, "slides", 4)
    await link(session, rows, (slides, 1), child)
    await link(session, rows, (slides, 2), rows.topic)  # the parent's: not the child's
    child.confidence = 4
    await tick(session, rows, child)

    data = await load_plan_data(session, user_id=user_a.id, now=NOW, days=7)

    assert [t.id for t in data.input.topics] == [child.id]
    facts = data.facts.topics[child.id]
    assert (facts.slide_pages, facts.subtopics, facts.confidence) == (1, 0, 4)
    # The parent's session (make_rows) isn't the child's.
    assert data.input.studied_minutes == {}


async def test_a_session_on_a_grandchild_counts_for_the_unit(
    session: AsyncSession, user_a: User
) -> None:
    rows = await make_rows(session, user_a)
    child = await child_of(session, rows, rows.topic, "Sagas")
    grandchild = await child_of(session, rows, child, "Compensation")
    await studied(session, user_a, rows.module, grandchild, 30 * 60 + 59)  # 30 min 59 s
    await tick(session, rows, rows.topic)

    data = await load_plan_data(session, user_id=user_a.id, now=NOW, days=7)

    # 50 min on the chapter (make_rows) + 30 min 59 s on the grandchild, floored once.
    assert data.input.studied_minutes == {rows.topic.id: 80}
    assert data.facts.topics[rows.topic.id].sessions == 2
    assert data.facts.topics[rows.topic.id].subtopics == 2


@pytest.mark.parametrize(
    ("own", "children", "expected"),
    [
        (None, (1, 2), (2, "subtopics")),  # 1.5 rounds half up
        (None, (2, 2, 3), (2, "subtopics")),  # 2.33
        (None, (None, 4), (4, "subtopics")),  # unrated ones don't count
        (5, (1, 1), (5, "yours")),  # its own rating wins
        (None, (None, None), (None, "none")),
    ],
)
async def test_the_units_confidence(
    session: AsyncSession,
    user_a: User,
    own: int | None,
    children: tuple[int | None, ...],
    expected: tuple[int | None, str],
) -> None:
    rows = await make_rows(session, user_a)
    rows.topic.confidence = own
    for n, rating in enumerate(children):
        child = await child_of(session, rows, rows.topic, f"Part {n}")
        child.confidence = rating
    await tick(session, rows, rows.topic)

    data = await load_plan_data(session, user_id=user_a.id, now=NOW, days=7)

    facts = data.facts.topics[rows.topic.id]
    assert (facts.confidence, facts.confidence_source) == expected
    assert data.input.topics[0].confidence == expected[0]


async def test_a_unit_inside_a_sooner_assessments_unit_is_planned_with_it(
    session: AsyncSession, user_a: User
) -> None:
    rows = await make_rows(session, user_a)
    child = await child_of(session, rows, rows.topic, "Sagas")
    await tick(session, rows, rows.topic)  # the sooner test covers the chapter
    later = await assessments.create_assessment(
        session,
        rows.module.id,
        AssessmentCreate(
            title="Assignment",
            kind="assignment",
            due_at=NOW + timedelta(days=6),
            topic_ids=[child.id],
        ),
        user_id=user_a.id,
    )

    request = await build_plan_input(session, user_id=user_a.id, now=NOW, days=7)

    by_id = {a.id: a for a in request.assessments}
    assert by_id[later.id].topic_ids == (rows.topic.id,)
    assert by_id[later.id].kind == "assignment"
    assert [t.id for t in request.topics] == [rows.topic.id]


async def test_another_users_pages_never_count(
    session: AsyncSession, user_a: User, user_b: User
) -> None:
    alice = await make_rows(session, user_a)
    bob = await make_rows(session, user_b)
    his = await material(session, bob, "slides", 5)
    for page in range(1, 6):
        await link(session, bob, (his, page), bob.topic)
    hers = await material(session, alice, "slides", 1)
    await link(session, alice, (hers, 1), alice.topic)
    await tick(session, alice, alice.topic)
    await tick(session, bob, bob.topic)

    data = await load_plan_data(session, user_id=user_a.id, now=NOW, days=7)

    assert data.facts.topics[alice.topic.id].slide_pages == 1
    assert set(data.facts.topics) == {alice.topic.id}


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
