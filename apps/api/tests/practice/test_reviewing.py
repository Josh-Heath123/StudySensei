"""Reviewing with FSRS and the review queue (ADR 0026): the state written, snapshots that
replay, a concurrent double review serialised by the lock, the queue's order and daily
allowance across local midnight (Europe/London's DST changes), settings and previews."""

import asyncio
import itertools
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.models import Module, PracticeItem, PracticeItemState, Review, User
from app.schemas.practice import ItemCreate, ReviewIn
from app.services.practice import items
from app.services.practice.filter import prompt_key
from app.services.practice.queue import EVERYTHING, Scope, queue_counts, review_queue, today_bounds
from app.services.practice.reviewing import review_item
from app.services.practice.scheduling import (
    MemoryState,
    ReviewEvent,
    SchedulingSettings,
    replay,
    schedule,
)
from tests.api.conftest import ClientFactory
from tests.practice.conftest import Practice

T0 = datetime(2026, 11, 2, 6, 0, tzinfo=UTC)


@pytest.fixture
async def api(client_as: ClientFactory, user_a: User) -> AsyncIterator[AsyncClient]:
    async with client_as(user_a) as client:
        yield client


async def card(
    session: AsyncSession, practice: Practice, prompt: str, *, created: datetime | None = None
) -> uuid.UUID:
    out = await items.create_item(
        session,
        ItemCreate(
            module_id=practice.module_id,
            topic_id=practice.chapter,
            kind="flashcard",
            prompt=prompt,
            answer="An answer.",
        ),
        user_id=practice.user_id,
    )
    if created is not None:
        await session.execute(
            update(PracticeItem).where(PracticeItem.id == out.id).values(created_at=created)
        )
        await session.commit()
    return out.id


async def review(
    session: AsyncSession, practice: Practice, item_id: uuid.UUID, grade: int, at: datetime
) -> None:
    await review_item(session, item_id, ReviewIn(grade=grade), user_id=practice.user_id, now=at)


async def stored(session: AsyncSession, item_id: uuid.UUID) -> PracticeItemState:
    row = await session.get(PracticeItemState, item_id, populate_existing=True)
    assert row is not None
    return row


async def test_a_review_writes_the_state_and_snapshots_that_replay(
    session: AsyncSession, practice: Practice, user_a: User
) -> None:
    item_id = await card(session, practice, "What is a state table?")
    plan = [(3, T0), (3, T0 + timedelta(minutes=10)), (1, T0 + timedelta(days=4))]
    for grade, at in plan[:2]:
        await review(session, practice, item_id, grade, at)
    # A new retention applies from the next review only.
    user_a.practice_desired_retention = 0.95
    await session.commit()
    await review(session, practice, item_id, *plan[2])

    rows = list(
        await session.scalars(
            select(Review).where(Review.item_id == item_id).order_by(Review.reviewed_at)
        )
    )
    assert [r.desired_retention for r in rows] == [0.9, 0.9, 0.95]
    assert rows[0].state_before is None
    for earlier, later in itertools.pairwise(rows):
        assert later.state_before == earlier.state_after
    state = await stored(session, item_id)
    expected = replay(
        [ReviewEvent(r.grade, r.reviewed_at, r.desired_retention) for r in rows],
        SchedulingSettings(),
    )
    assert expected is not None
    assert MemoryState.from_snapshot(rows[-1].state_after or {}) == expected
    assert (state.state, state.due, state.stability, state.reps, state.lapses) == (
        expected.state,
        expected.due,
        expected.stability,
        3,
        expected.lapses,
    )
    assert {r.fsrs_version for r in rows} == {"fsrs 6.3.3"}
    for r in rows:
        after = MemoryState.from_snapshot(r.state_after or {})
        assert r.scheduled_days == (after.due - r.reviewed_at).days
    assert rows[0].scheduled_days == 0  # the first learning step is minutes


async def test_a_concurrent_double_review_is_serialised(engine: AsyncEngine) -> None:
    """Two reviews of one new item at once, on two connections: without the lock both would
    read "new" and write reps 1. Committed for real, so it cleans up after itself."""
    async with AsyncSession(engine, expire_on_commit=False) as setup:
        user = User(email=f"race-{uuid.uuid4()}@example.test", display_name="Race")
        setup.add(user)
        await setup.flush()
        module = Module(user_id=user.id, code="RACE1", name="Race", colour="#FF7A3D")
        setup.add(module)
        await setup.flush()
        item = PracticeItem(
            user_id=user.id,
            module_id=module.id,
            kind="flashcard",
            prompt="What is a race?",
            answer="Two at once.",
            origin="user",
            status="active",
            prompt_key=prompt_key("What is a race?"),
        )
        setup.add(item)
        await setup.commit()
        user_id, item_id = user.id, item.id
    try:

        async def one() -> None:
            async with AsyncSession(engine, expire_on_commit=False) as own:
                await review_item(own, item_id, ReviewIn(grade=3), user_id=user_id, now=T0)

        await asyncio.gather(one(), one())
        async with AsyncSession(engine) as check:
            rows = list(
                await check.scalars(
                    select(Review).where(Review.item_id == item_id).order_by(Review.created_at)
                )
            )
            state = await check.get(PracticeItemState, item_id)
            assert len(rows) == 2 and state is not None and state.reps == 2
            befores = [r.state_before for r in rows]
            assert befores.count(None) == 1  # only one of them saw a new item
            first = next(r for r in rows if r.state_before is None)
            second = next(r for r in rows if r.state_before is not None)
            assert second.state_before == first.state_after
    finally:
        async with AsyncSession(engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == user_id))
            await cleanup.commit()


async def test_the_queue_puts_due_items_first_then_new_ones_up_to_the_allowance(
    session: AsyncSession, practice: Practice, user_a: User
) -> None:
    user_a.practice_new_per_day = 2
    await session.commit()
    old = await card(session, practice, "Oldest new card?", created=T0 - timedelta(days=3))
    mid = await card(session, practice, "Middle new card?", created=T0 - timedelta(days=2))
    late = await card(session, practice, "Newest new card?", created=T0 - timedelta(days=1))
    a = await card(session, practice, "Reviewed card A?", created=T0 - timedelta(days=9))
    b = await card(session, practice, "Reviewed card B?", created=T0 - timedelta(days=9))
    yesterday = T0 - timedelta(days=1)
    await review(session, practice, a, 1, yesterday)  # due a minute later: overdue
    await review(session, practice, b, 3, yesterday - timedelta(hours=1))  # due 10 min later
    suspended = await card(session, practice, "Suspended card?", created=T0 - timedelta(days=5))
    await session.execute(
        update(PracticeItem).where(PracticeItem.id == suspended).values(status="suspended")
    )
    await session.commit()

    found, counts = await review_queue(session, user_id=practice.user_id, now=T0)
    # Due first, oldest due first (b's due is earlier); then new, oldest first. Yesterday's
    # two first reviews don't count against today's allowance.
    assert [i.id for i in found] == [b, a, old, mid]
    assert (counts.due_now, counts.new_today_left, counts.new_total) == (2, 2, 3)
    assert counts.next_due_at is None

    # Reviewing one new item today uses one of the two.
    await review(session, practice, old, 3, T0)
    found, counts = await review_queue(session, user_id=practice.user_id, now=T0)
    assert [i.id for i in found] == [b, a, mid]
    assert (counts.new_today_left, counts.new_total) == (1, 2)
    assert counts.next_due_at == T0 + timedelta(minutes=10)
    assert late not in [i.id for i in found]
    # The limit holds, and so do the module and topic filters.
    found, _ = await review_queue(session, user_id=practice.user_id, now=T0, limit=1)
    assert [i.id for i in found] == [b]
    found, _ = await review_queue(
        session, user_id=practice.user_id, now=T0, scope=Scope(topic_id=practice.other)
    )
    assert found == []


@pytest.mark.parametrize(
    ("first", "later", "same_day"),
    [
        # Spring forward (29 Mar 2026, 01:00 UTC): 23:30 GMT on the 28th, then 00:30 GMT on the
        # 29th: a new day.
        ("2026-03-28T23:30:00+00:00", "2026-03-29T00:30:00+00:00", False),
        # Fall back (25 Oct 2026, 01:00 UTC): 00:30 BST on the 25th, then 23:30 GMT still on
        # the 25th (a fixed UTC+1 would call it the 26th).
        ("2026-10-24T23:30:00+00:00", "2026-10-25T23:30:00+00:00", True),
        ("2026-10-24T22:30:00+00:00", "2026-10-24T23:30:00+00:00", False),
    ],
)
async def test_the_daily_allowance_follows_local_midnight_across_dst(
    session: AsyncSession,
    practice: Practice,
    user_a: User,
    first: str,
    later: str,
    same_day: bool,
) -> None:
    user_a.timezone, user_a.practice_new_per_day = "Europe/London", 1
    await session.commit()
    item_id = await card(session, practice, "A card for the allowance?")
    await card(session, practice, "Another card waiting?")
    await review(session, practice, item_id, 3, datetime.fromisoformat(first))
    counts = await queue_counts(
        session, user_id=practice.user_id, now=datetime.fromisoformat(later), scope=EVERYTHING
    )
    assert counts.new_today_left == (0 if same_day else 1)


def test_today_bounds_in_london() -> None:
    start, end = today_bounds(datetime(2026, 10, 25, 12, 0, tzinfo=UTC), "Europe/London")
    assert start.astimezone(UTC) == datetime(2026, 10, 24, 23, 0, tzinfo=UTC)
    assert end.astimezone(UTC) == datetime(2026, 10, 26, 0, 0, tzinfo=UTC)  # a 25-hour day


async def test_settings_are_validated(api: AsyncClient) -> None:
    assert (await api.get("/practice/settings")).json() == {
        "new_per_day": 20,
        "desired_retention": 0.9,
    }
    changed = await api.patch(
        "/practice/settings", json={"new_per_day": 0, "desired_retention": 0.97}
    )
    assert changed.json() == {"new_per_day": 0, "desired_retention": 0.97}
    for bad in (
        {"new_per_day": -1},
        {"new_per_day": 201},
        {"desired_retention": 0.79},
        {"desired_retention": 0.98},
        {"new_per_day": None},
        {"other": 1},
    ):
        assert (await api.patch("/practice/settings", json=bad)).status_code == 422, bad


async def test_preview_labels_and_the_review_response(api: AsyncClient, practice: Practice) -> None:
    item = (
        await api.post(
            "/practice/items",
            json={
                "module_id": str(practice.module_id),
                "kind": "flashcard",
                "prompt": "What is a packet filter?",
                "answer": "A rule check on each packet.",
            },
        )
    ).json()
    assert item["memory"] == {
        "state": "new",
        "due": None,
        "stability": None,
        "difficulty": None,
        "retrievability": None,
        "reps": 0,
        "lapses": 0,
    }
    preview = (await api.get(f"/practice/items/{item['id']}/preview")).json()
    options = {o["name"]: o for o in preview["options"]}
    assert [o["grade"] for o in preview["options"]] == [1, 2, 3, 4]
    assert (options["again"]["interval"], options["hard"]["interval"]) == ("1 min", "6 min")
    assert options["good"]["interval"] == "10 min"
    assert options["easy"]["interval"].endswith("days")
    # What the preview says is what a review then does.
    done = await api.post(f"/practice/items/{item['id']}/reviews", json={"grade": 3})
    assert done.status_code == 201
    body = done.json()
    assert body["scheduled"]["state"] == "learning" and body["scheduled"]["scheduled_days"] == 0
    due = datetime.fromisoformat(body["scheduled"]["due"])
    reviewed = datetime.fromisoformat(body["review"]["reviewed_at"])
    assert due - reviewed == timedelta(minutes=10)
    assert body["counts"]["new_total"] == 0 and body["counts"]["due_now"] == 0
    listed = (await api.get("/practice/items")).json()["items"][0]["memory"]
    assert (listed["state"], listed["reps"]) == ("learning", 1)
    assert listed["retrievability"]["label"] == "estimated"
    assert listed["retrievability"]["sample_size"] == 1
    queue = (await api.get("/practice/queue")).json()
    assert queue["counts"]["next_due_at"] is not None
    assert (await api.get("/practice/queue", params={"limit": 101})).status_code == 422


def test_schedule_and_the_service_agree_on_a_first_review() -> None:
    state, days = schedule(None, 3, T0, SchedulingSettings())
    assert (state.state, days, state.due - T0) == ("learning", 0, timedelta(minutes=10))


async def test_listed_reviews_carry_their_schedule_and_the_state_after(
    api: AsyncClient, session: AsyncSession, practice: Practice
) -> None:
    """For the practice screen's "next due": each review's days, retention and the state and
    due it led to; null for a review from before scheduling (task 1)."""
    item_id = await card(session, practice, "What does a state table hold?")
    session.add(
        Review(
            user_id=practice.user_id,
            item_id=item_id,
            reviewed_at=T0 - timedelta(days=1),
            grade=2,
            marked_by="self",
        )
    )
    await session.commit()
    await review(session, practice, item_id, 3, T0)
    newest, oldest = (await api.get(f"/practice/items/{item_id}/reviews")).json()
    assert newest["scheduled_days"] == 0
    assert newest["desired_retention"] == 0.9
    assert newest["after"]["state"] == "learning"
    assert datetime.fromisoformat(newest["after"]["due"]) == T0 + timedelta(minutes=10)
    assert (oldest["scheduled_days"], oldest["desired_retention"], oldest["after"]) == (
        None,
        None,
        None,
    )

