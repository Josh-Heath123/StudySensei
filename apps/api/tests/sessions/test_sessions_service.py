"""Session service on real Postgres: idempotency, offline replay, one open session, reflection."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SessionEvent, SessionTopicRating, StudySession
from app.schemas.academics import ModuleCreate, TopicCreate
from app.schemas.sessions import EventBatch, ReflectionIn, SessionStart
from app.services.academics import modules, topics
from app.services.errors import Conflict, Invalid, NotFound
from app.services.sessions import sessions
from tests.academics.conftest import Rows

T0 = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def start_body(
    rows: Rows, *, event_id: uuid.UUID | None = None, topic: bool = True
) -> SessionStart:
    return SessionStart.model_validate(
        {
            "module_id": rows.module.id,
            "topic_id": rows.topic.id if topic else None,
            "start": {"id": event_id or uuid.uuid4(), "occurred_at": at(0)},
        }
    )


def events(*steps: tuple[str, float] | tuple[str, float, uuid.UUID]) -> EventBatch:
    """A batch from (type, minutes after T0[, id]); ids are random unless given."""
    items: list[dict[str, Any]] = []
    for step in steps:
        kind, minutes, *given = step
        items.append(
            {"id": given[0] if given else uuid.uuid4(), "type": kind, "occurred_at": at(minutes)}
        )
    return EventBatch.model_validate({"events": items})


async def open_session(session: AsyncSession, rows: Rows) -> StudySession:
    study, created = await sessions.start_session(session, start_body(rows), user_id=rows.user.id)
    assert created
    return study


async def test_start_opens_an_active_session_with_its_start_event(
    session: AsyncSession, alice: Rows
) -> None:
    study = await open_session(session, alice)

    assert (study.state, study.started_at, study.ended_at) == ("active", at(0), None)
    assert (study.active_seconds, study.break_seconds) == (0, 0)
    log = await sessions.events_of(session, study.id, user_id=alice.user.id)
    assert [(e.type, e.occurred_at) for e in log] == [("start", at(0))]
    assert await sessions.get_active_session(session, user_id=alice.user.id) == study


async def test_resending_the_same_start_returns_the_same_session(
    session: AsyncSession, alice: Rows
) -> None:
    body = start_body(alice)
    first, created = await sessions.start_session(session, body, user_id=alice.user.id)
    again, created_again = await sessions.start_session(session, body, user_id=alice.user.id)

    assert (created, created_again) == (True, False)
    assert again.id == first.id


async def test_reusing_a_start_id_with_other_details_conflicts(
    session: AsyncSession, alice: Rows
) -> None:
    event_id = uuid.uuid4()
    await sessions.start_session(
        session, start_body(alice, event_id=event_id), user_id=alice.user.id
    )

    with pytest.raises(Conflict):
        await sessions.start_session(
            session, start_body(alice, event_id=event_id, topic=False), user_id=alice.user.id
        )


async def test_only_one_session_can_be_open_per_user(
    session: AsyncSession, alice: Rows, bob: Rows
) -> None:
    await open_session(session, alice)

    with pytest.raises(Conflict, match="still open"):
        await sessions.start_session(session, start_body(alice), user_id=alice.user.id)
    # Bob's sessions are his own business.
    await open_session(session, bob)


async def test_a_new_session_can_start_once_the_open_one_ends(
    session: AsyncSession, alice: Rows
) -> None:
    study = await open_session(session, alice)
    await sessions.add_events(session, study.id, events(("end", 10)), user_id=alice.user.id)

    assert await sessions.get_active_session(session, user_id=alice.user.id) is None
    await open_session(session, alice)


async def test_topic_must_be_in_the_sessions_module(session: AsyncSession, alice: Rows) -> None:
    other = await modules.create_module(
        session, ModuleCreate(code="COS301", name="Other"), user_id=alice.user.id
    )
    body = SessionStart.model_validate(
        {
            "module_id": other.id,
            "topic_id": alice.topic.id,
            "start": {"id": uuid.uuid4(), "occurred_at": at(0)},
        }
    )

    with pytest.raises(Invalid):
        await sessions.start_session(session, body, user_id=alice.user.id)


async def test_events_update_state_and_totals(session: AsyncSession, alice: Rows) -> None:
    study = await open_session(session, alice)
    uid = alice.user.id

    study = await sessions.add_events(
        session, study.id, events(("pause", 10), ("resume", 12)), user_id=uid
    )
    assert (study.state, study.active_seconds, study.last_event_at) == ("active", 600, at(12))

    study = await sessions.add_events(
        session, study.id, events(("break_start", 30), ("break_end", 35), ("end", 50)), user_id=uid
    )
    assert study.state == "ended"
    assert study.ended_at == at(50)
    assert (study.active_seconds, study.break_seconds) == ((10 + 18 + 15) * 60, 5 * 60)


async def test_resending_events_is_a_no_op(session: AsyncSession, alice: Rows) -> None:
    study = await open_session(session, alice)
    batch = events(("pause", 10), ("resume", 12))

    await sessions.add_events(session, study.id, batch, user_id=alice.user.id)
    study = await sessions.add_events(session, study.id, batch, user_id=alice.user.id)

    assert len(await sessions.events_of(session, study.id, user_id=alice.user.id)) == 3
    assert study.active_seconds == 600


async def test_an_event_repeated_within_a_batch_is_stored_once(
    session: AsyncSession, alice: Rows
) -> None:
    study = await open_session(session, alice)
    pause = uuid.uuid4()

    await sessions.add_events(
        session, study.id, events(("pause", 10, pause), ("pause", 10, pause)), user_id=alice.user.id
    )

    assert len(await sessions.events_of(session, study.id, user_id=alice.user.id)) == 2


async def test_an_event_id_reused_with_other_details_conflicts(
    session: AsyncSession, alice: Rows
) -> None:
    study = await open_session(session, alice)
    pause = uuid.uuid4()
    await sessions.add_events(
        session, study.id, events(("pause", 10, pause)), user_id=alice.user.id
    )

    with pytest.raises(Conflict):
        await sessions.add_events(
            session, study.id, events(("pause", 11, pause)), user_id=alice.user.id
        )
    with pytest.raises(Conflict):
        await sessions.add_events(
            session,
            study.id,
            events(("pause", 10, pause), ("pause", 12, pause)),
            user_id=alice.user.id,
        )


async def test_an_event_id_from_another_of_your_sessions_conflicts(
    session: AsyncSession, alice: Rows
) -> None:
    study = await open_session(session, alice)
    reused = alice.start_event_id  # the start of her ended session

    with pytest.raises(Conflict):
        await sessions.add_events(
            session, study.id, events(("pause", 10, reused)), user_id=alice.user.id
        )


async def test_a_batch_with_an_impossible_event_saves_nothing(
    session: AsyncSession, alice: Rows
) -> None:
    study = await open_session(session, alice)

    with pytest.raises(Invalid):
        await sessions.add_events(
            session, study.id, events(("pause", 10), ("break_start", 11)), user_id=alice.user.id
        )

    assert len(await sessions.events_of(session, study.id, user_id=alice.user.id)) == 1
    assert (
        await sessions.get_study_session(session, study.id, user_id=alice.user.id)
    ).state == "active"


async def test_a_late_offline_batch_is_merged_in_time_order(
    session: AsyncSession, alice: Rows
) -> None:
    study = await open_session(session, alice)
    uid = alice.user.id
    # The device went offline at minute 10; the end got through first, the rest later.
    await sessions.add_events(session, study.id, events(("pause", 10)), user_id=uid)
    await sessions.add_events(session, study.id, events(("end", 50)), user_id=uid)

    study = await sessions.add_events(
        session,
        study.id,
        events(("break_end", 30), ("resume", 20), ("break_start", 25)),
        user_id=uid,
    )

    log = await sessions.events_of(session, study.id, user_id=uid)
    assert [e.type for e in log] == [
        "start", "pause", "resume", "break_start", "break_end", "end",
    ]  # fmt: skip
    assert study.state == "ended"
    assert (study.active_seconds, study.break_seconds) == ((10 + 5 + 20) * 60, 5 * 60)


async def test_an_event_before_the_start_is_invalid(session: AsyncSession, alice: Rows) -> None:
    study = await open_session(session, alice)

    with pytest.raises(Invalid, match="before the session's start"):
        await sessions.add_events(session, study.id, events(("pause", -1)), user_id=alice.user.id)


async def test_an_event_in_the_future_is_invalid(session: AsyncSession, alice: Rows) -> None:
    study = await open_session(session, alice)
    future = (datetime.now(UTC) + timedelta(minutes=10) - T0).total_seconds() / 60

    with pytest.raises(Invalid, match="future"):
        await sessions.add_events(
            session, study.id, events(("pause", future)), user_id=alice.user.id
        )


async def test_reflection_needs_an_ended_session(session: AsyncSession, alice: Rows) -> None:
    study = await open_session(session, alice)

    with pytest.raises(Invalid, match="ended"):
        await sessions.set_reflection(
            session, study.id, ReflectionIn(focus_rating=3), user_id=alice.user.id
        )


async def test_reflection_is_replaced_as_a_whole(session: AsyncSession, alice: Rows) -> None:
    uid = alice.user.id
    study_id = alice.study_session.id
    second = await topics.create_topic(
        session, alice.module.id, TopicCreate(name="Events"), user_id=uid
    )
    ratings = [{"topic_id": second.id, "confidence": 5}]

    study = await sessions.set_reflection(
        session,
        study_id,
        ReflectionIn.model_validate(
            {"focus_rating": 2, "covered_notes": "CQRS", "topic_ratings": ratings}
        ),
        user_id=uid,
    )

    assert (study.focus_rating, study.covered_notes) == (2, "CQRS")
    saved = (await sessions.ratings_for(session, [study_id], user_id=uid))[study_id]
    assert [(r.topic_id, r.confidence) for r in saved] == [(second.id, 5)]


async def test_reflection_rating_another_modules_topic_is_invalid(
    session: AsyncSession, alice: Rows
) -> None:
    uid = alice.user.id
    other = await modules.create_module(
        session, ModuleCreate(code="COS301", name="Other"), user_id=uid
    )
    stray = await topics.create_topic(session, other.id, TopicCreate(name="Stray"), user_id=uid)
    body = ReflectionIn.model_validate(
        {"focus_rating": 3, "topic_ratings": [{"topic_id": stray.id, "confidence": 2}]}
    )

    with pytest.raises(Invalid):
        await sessions.set_reflection(session, alice.study_session.id, body, user_id=uid)


async def test_reflection_rating_someone_elses_topic_is_not_found(
    session: AsyncSession, alice: Rows, bob: Rows
) -> None:
    body = ReflectionIn.model_validate(
        {"focus_rating": 3, "topic_ratings": [{"topic_id": alice.topic.id, "confidence": 2}]}
    )

    with pytest.raises(NotFound):
        await sessions.set_reflection(session, bob.study_session.id, body, user_id=bob.user.id)


async def test_deleting_the_topic_keeps_the_session_without_it(
    session: AsyncSession, alice: Rows
) -> None:
    await topics.delete_topic(session, alice.topic.id, user_id=alice.user.id)

    study = await session.scalar(
        select(StudySession)
        .where(StudySession.id == alice.study_session.id)
        .execution_options(populate_existing=True)
    )
    assert study is not None
    assert (study.topic_id, study.module_id) == (None, alice.module.id)
    # Its rating of that topic goes with the topic.
    ratings = await sessions.ratings_for(session, [study.id], user_id=alice.user.id)
    assert ratings[study.id] == []


async def test_deleting_the_module_deletes_its_sessions_and_events(
    session: AsyncSession, alice: Rows
) -> None:
    await modules.delete_module(session, alice.module.id, user_id=alice.user.id)

    assert (
        await session.scalar(select(StudySession).where(StudySession.user_id == alice.user.id))
        is None
    )
    assert (
        await session.scalar(select(SessionEvent).where(SessionEvent.user_id == alice.user.id))
        is None
    )


async def test_deleting_a_session_removes_its_events(session: AsyncSession, alice: Rows) -> None:
    await sessions.delete_session(session, alice.study_session.id, user_id=alice.user.id)

    assert (
        await session.scalar(select(SessionEvent).where(SessionEvent.user_id == alice.user.id))
        is None
    )


# --- Postgres rejects cross-user and cross-module links on its own -------------------


async def test_db_rejects_an_event_on_another_users_session(
    session: AsyncSession, alice: Rows, bob: Rows
) -> None:
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add(
                SessionEvent(
                    user_id=bob.user.id,
                    id=uuid.uuid4(),
                    session_id=alice.study_session.id,
                    type="pause",
                    occurred_at=at(1),
                )
            )
            await session.flush()


async def test_db_rejects_a_rating_for_another_modules_topic(
    session: AsyncSession, alice: Rows, bob: Rows
) -> None:
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add(
                SessionTopicRating(
                    session_id=alice.study_session.id,
                    topic_id=bob.topic.id,
                    module_id=alice.module.id,
                    confidence=3,
                )
            )
            await session.flush()


async def test_event_ids_are_only_unique_per_user(
    session: AsyncSession, alice: Rows, bob: Rows
) -> None:
    # Bob happening to reuse one of Alice's event ids neither fails nor touches hers.
    body = start_body(bob, event_id=alice.start_event_id)
    study, created = await sessions.start_session(session, body, user_id=bob.user.id)

    assert created
    assert study.user_id == bob.user.id
