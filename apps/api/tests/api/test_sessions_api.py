"""Study session endpoints: start, resume after reload, events, reflection, history."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient

from tests.academics.conftest import Rows

T0 = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)


def at(minutes: float) -> str:
    return (T0 + timedelta(minutes=minutes)).isoformat()


def start_body(rows: Rows, event_id: uuid.UUID | None = None) -> dict[str, Any]:
    return {
        "module_id": str(rows.module.id),
        "topic_id": str(rows.topic.id),
        "start": {"id": str(event_id or uuid.uuid4()), "occurred_at": at(0)},
    }


def batch(*steps: tuple[str, float]) -> dict[str, Any]:
    return {
        "events": [
            {"id": str(uuid.uuid4()), "type": kind, "occurred_at": at(minutes)}
            for kind, minutes in steps
        ]
    }


async def test_active_is_null_until_a_session_starts(alice_api: AsyncClient, alice: Rows) -> None:
    response = await alice_api.get("/sessions/active")
    assert (response.status_code, response.json()) == (200, None)

    started = await alice_api.post("/sessions", json=start_body(alice))
    assert started.status_code == 201

    active = (await alice_api.get("/sessions/active")).json()
    assert active["id"] == started.json()["id"]
    assert active["state"] == "active"
    assert [e["type"] for e in active["events"]] == ["start"]


async def test_retrying_the_start_returns_200_and_the_same_session(
    alice_api: AsyncClient, alice: Rows
) -> None:
    body = start_body(alice)
    first = await alice_api.post("/sessions", json=body)
    again = await alice_api.post("/sessions", json=body)

    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json()["id"] == first.json()["id"]


async def test_a_second_open_session_is_a_409(alice_api: AsyncClient, alice: Rows) -> None:
    await alice_api.post("/sessions", json=start_body(alice))

    response = await alice_api.post("/sessions", json=start_body(alice))

    assert response.status_code == 409
    assert "still open" in response.json()["detail"]


async def test_reload_resume_end_and_reflect(alice_api: AsyncClient, alice: Rows) -> None:
    session_id = (await alice_api.post("/sessions", json=start_body(alice))).json()["id"]
    await alice_api.post(f"/sessions/{session_id}/events", json=batch(("break_start", 25)))

    # A reload: the page only knows to ask for the open session.
    resumed = (await alice_api.get("/sessions/active")).json()
    assert resumed["id"] == session_id
    assert resumed["state"] == "on_break"
    assert datetime.fromisoformat(resumed["last_event_at"]) == datetime.fromisoformat(at(25))
    assert resumed["active_seconds"] == 25 * 60

    ended = await alice_api.post(
        f"/sessions/{session_id}/events", json=batch(("break_end", 30), ("end", 50))
    )
    assert ended.status_code == 200
    body = ended.json()
    assert body["state"] == "ended"
    assert (body["active_seconds"], body["break_seconds"]) == (45 * 60, 5 * 60)
    assert [e["type"] for e in body["events"]] == [
        "start", "break_start", "break_end", "end",
    ]  # fmt: skip

    reflection = {
        "focus_rating": 4,
        "covered_notes": "Saga pattern",
        "topic_ratings": [{"topic_id": str(alice.topic.id), "confidence": 2}],
    }
    reflected = await alice_api.put(f"/sessions/{session_id}/reflection", json=reflection)
    assert reflected.status_code == 200
    assert reflected.json()["focus_rating"] == 4
    assert reflected.json()["topic_ratings"] == [{"topic_id": str(alice.topic.id), "confidence": 2}]
    assert (await alice_api.get("/sessions/active")).json() is None


async def test_resent_events_change_nothing(alice_api: AsyncClient, alice: Rows) -> None:
    session_id = (await alice_api.post("/sessions", json=start_body(alice))).json()["id"]
    events = batch(("pause", 10), ("resume", 15))

    first = await alice_api.post(f"/sessions/{session_id}/events", json=events)
    again = await alice_api.post(f"/sessions/{session_id}/events", json=events)

    assert first.json() == again.json()


async def test_an_impossible_event_is_a_422(alice_api: AsyncClient, alice: Rows) -> None:
    session_id = (await alice_api.post("/sessions", json=start_body(alice))).json()["id"]

    response = await alice_api.post(f"/sessions/{session_id}/events", json=batch(("resume", 5)))

    assert response.status_code == 422
    assert "resume while active" in response.json()["detail"]


async def test_clients_cannot_send_starts_or_durations(alice_api: AsyncClient, alice: Rows) -> None:
    session_id = alice.study_session.id
    start = batch(("start", 0))
    with_duration = batch(("pause", 1))
    with_duration["events"][0]["active_seconds"] = 999

    bodies: list[dict[str, Any]] = [start, with_duration, {"events": []}]
    for body in bodies:
        response = await alice_api.post(f"/sessions/{session_id}/events", json=body)
        assert response.status_code == 422


async def test_reflecting_on_an_open_session_is_a_422(alice_api: AsyncClient, alice: Rows) -> None:
    session_id = (await alice_api.post("/sessions", json=start_body(alice))).json()["id"]

    response = await alice_api.put(f"/sessions/{session_id}/reflection", json={"focus_rating": 3})

    assert response.status_code == 422


async def test_reflection_ratings_are_validated(alice_api: AsyncClient, alice: Rows) -> None:
    path = f"/sessions/{alice.study_session.id}/reflection"
    rating = {"topic_id": str(alice.topic.id), "confidence": 3}

    for body in (
        {"focus_rating": 0},
        {"focus_rating": 6},
        {"focus_rating": 3, "topic_ratings": [{**rating, "confidence": 9}]},
        {"focus_rating": 3, "topic_ratings": [rating, rating]},
    ):
        assert (await alice_api.put(path, json=body)).status_code == 422


async def test_module_history_is_newest_first(alice_api: AsyncClient, alice: Rows) -> None:
    newer = (await alice_api.post("/sessions", json=start_body(alice))).json()["id"]

    page = (await alice_api.get(f"/modules/{alice.module.id}/sessions")).json()

    assert (page["total"], page["limit"], page["offset"]) == (2, 20, 0)
    history = page["items"]
    assert [s["id"] for s in history] == [newer, str(alice.study_session.id)]
    assert history[1]["topic_ratings"] == [{"topic_id": str(alice.topic.id), "confidence": 3}]
    assert "events" not in history[1]


async def ended_session(api: AsyncClient, rows: Rows, started: datetime) -> str:
    """A 30-minute session (no breaks) that started at `started`."""
    body = {
        "module_id": str(rows.module.id),
        "start": {"id": str(uuid.uuid4()), "occurred_at": started.isoformat()},
    }
    session_id: str = (await api.post("/sessions", json=body)).json()["id"]
    end = {
        "id": str(uuid.uuid4()),
        "type": "end",
        "occurred_at": (started + timedelta(minutes=30)).isoformat(),
    }
    await api.post(f"/sessions/{session_id}/events", json={"events": [end]})
    return session_id


async def test_module_history_is_paginated(alice_api: AsyncClient, alice: Rows) -> None:
    older = [await ended_session(alice_api, alice, T0 - timedelta(days=days)) for days in (3, 2, 1)]
    path = f"/modules/{alice.module.id}/sessions"

    first = (await alice_api.get(path, params={"limit": 2})).json()
    second = (await alice_api.get(path, params={"limit": 2, "offset": 2})).json()

    newest_first = [str(alice.study_session.id), *reversed(older)]
    assert first["total"] == second["total"] == 4
    assert [s["id"] for s in first["items"]] == newest_first[:2]
    assert [s["id"] for s in second["items"]] == newest_first[2:]
    assert second["offset"] == 2


async def test_module_history_puts_the_open_session_first(
    alice_api: AsyncClient, alice: Rows
) -> None:
    # An open session whose start (from an offline device) is older than an ended one.
    body = start_body(alice)
    body["start"]["occurred_at"] = (T0 - timedelta(days=1)).isoformat()
    open_id = (await alice_api.post("/sessions", json=body)).json()["id"]

    items = (await alice_api.get(f"/modules/{alice.module.id}/sessions")).json()["items"]

    assert [(s["id"], s["state"]) for s in items] == [
        (open_id, "active"),
        (str(alice.study_session.id), "ended"),
    ]


async def test_module_history_rejects_bad_page_sizes(alice_api: AsyncClient, alice: Rows) -> None:
    path = f"/modules/{alice.module.id}/sessions"
    for params in ({"limit": 0}, {"limit": 101}, {"offset": -1}):
        assert (await alice_api.get(path, params=params)).status_code == 422


async def test_summary_measures_all_time_and_this_week(alice_api: AsyncClient, alice: Rows) -> None:
    week_start = datetime.now(UTC) - timedelta(days=3)
    await ended_session(alice_api, alice, week_start - timedelta(days=2))  # last week

    response = await alice_api.get(
        f"/modules/{alice.module.id}/sessions/summary",
        params={"week_start": week_start.isoformat()},
    )

    assert response.status_code == 200
    summary = response.json()
    assert summary["session_count"] == 2
    assert summary["active_seconds"] == (50 + 30) * 60
    assert summary["week_active_seconds"] == 50 * 60  # only the fixture session (2 h ago)
    assert datetime.fromisoformat(summary["week_start"]) == week_start


async def test_summary_needs_a_timezone_aware_week_start(
    alice_api: AsyncClient, alice: Rows
) -> None:
    path = f"/modules/{alice.module.id}/sessions/summary"
    assert (await alice_api.get(path)).status_code == 422
    naive = {"week_start": "2026-11-09T00:00:00"}
    assert (await alice_api.get(path, params=naive)).status_code == 422


async def test_summary_of_a_module_without_sessions_is_zero(alice_api: AsyncClient) -> None:
    module = (await alice_api.post("/modules", json={"code": "NEW101", "name": "New"})).json()

    summary = (
        await alice_api.get(
            f"/modules/{module['id']}/sessions/summary",
            params={"week_start": "2026-11-09T00:00:00+02:00"},
        )
    ).json()

    assert (summary["session_count"], summary["active_seconds"]) == (0, 0)
    assert summary["week_active_seconds"] == 0


async def test_delete_discards_the_session(alice_api: AsyncClient, alice: Rows) -> None:
    session_id = alice.study_session.id

    assert (await alice_api.delete(f"/sessions/{session_id}")).status_code == 204
    assert (await alice_api.get(f"/sessions/{session_id}")).status_code == 404
