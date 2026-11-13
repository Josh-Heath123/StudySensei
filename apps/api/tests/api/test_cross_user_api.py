"""Over HTTP, Bob can't reach Alice's modules, topics, assessments, tasks or study sessions.

Every request Bob makes with one of Alice's IDs must get exactly the response
a random, non-existent ID gets, so he can't even tell her rows exist. Afterwards
Alice's data must be unchanged.
"""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient

from tests.academics.conftest import Rows

# A start for POST /sessions; it never gets far enough to be stored.
START = {"id": str(uuid.uuid4()), "occurred_at": "2026-11-01T08:00:00Z"}

# (method, path template, body). {module}/{topic}/{assessment}/{task}/{session} are
# filled with Alice's IDs, or with random UUIDs for the baseline. {my_*} are always Bob's.
ATTEMPTS: list[tuple[str, str, dict[str, Any] | None]] = [
    ("GET", "/modules/{module}", None),
    ("PATCH", "/modules/{module}", {"name": "Hacked"}),
    ("DELETE", "/modules/{module}", None),
    ("GET", "/modules/{module}/topics", None),
    ("POST", "/modules/{module}/topics", {"name": "Planted"}),
    ("PATCH", "/topics/{topic}", {"name": "Hacked"}),
    ("POST", "/topics/{topic}/move", {"parent_id": None, "position": 0}),
    ("DELETE", "/topics/{topic}", None),
    # Using her topic as a parent, from Bob's own side.
    ("POST", "/topics/{my_topic}/move", {"parent_id": "{topic}", "position": 0}),
    # Assessments
    ("GET", "/modules/{module}/assessments", None),
    ("GET", "/assessments/{assessment}", None),
    ("PATCH", "/assessments/{assessment}", {"title": "Hacked"}),
    ("DELETE", "/assessments/{assessment}", None),
    ("POST", "/modules/{module}/assessments", {"title": "Planted", "kind": "exam"}),
    # His assessment covering her topic (on create and on update).
    (
        "POST",
        "/modules/{my_module}/assessments",
        {"title": "X", "kind": "exam", "topic_ids": ["{topic}"]},
    ),
    ("PATCH", "/assessments/{my_assessment}", {"topic_ids": ["{topic}"]}),
    # Tasks
    ("GET", "/modules/{module}/tasks", None),
    ("GET", "/tasks/{task}", None),
    ("PATCH", "/tasks/{task}", {"status": "done"}),
    ("DELETE", "/tasks/{task}", None),
    ("POST", "/modules/{module}/tasks", {"title": "Planted"}),
    # His task on her assessment (on create and on update).
    ("POST", "/modules/{my_module}/tasks", {"title": "X", "assessment_id": "{assessment}"}),
    ("PATCH", "/tasks/{my_task}", {"assessment_id": "{assessment}"}),
    # Study sessions
    ("GET", "/sessions/{session}", None),
    (
        "POST",
        "/sessions/{session}/events",
        {
            "events": [
                {"id": str(uuid.uuid4()), "type": "pause", "occurred_at": START["occurred_at"]}
            ]
        },
    ),
    ("PUT", "/sessions/{session}/reflection", {"focus_rating": 1}),
    ("DELETE", "/sessions/{session}", None),
    ("GET", "/modules/{module}/sessions", None),
    ("POST", "/sessions", {"module_id": "{module}", "start": START}),
    # His session on her topic, and his reflection rating her topic.
    ("POST", "/sessions", {"module_id": "{my_module}", "topic_id": "{topic}", "start": START}),
    (
        "PUT",
        "/sessions/{my_session}/reflection",
        {"focus_rating": 3, "topic_ratings": [{"topic_id": "{topic}", "confidence": 3}]},
    ),
]


def fill(value: Any, ids: dict[str, str]) -> Any:
    if isinstance(value, str):
        return value.format(**ids)
    if isinstance(value, dict):
        return {k: fill(v, ids) for k, v in value.items()}
    if isinstance(value, list):
        return [fill(v, ids) for v in value]
    return value


def ids_of(alice: Rows, bob: Rows) -> tuple[dict[str, str], dict[str, str]]:
    """(Alice's real IDs, the same keys with random IDs). Bob's own IDs are in both."""
    mine = {
        "my_module": str(bob.module.id),
        "my_topic": str(bob.topic.id),
        "my_assessment": str(bob.assessment.id),
        "my_task": str(bob.task.id),
        "my_session": str(bob.study_session.id),
    }
    hers = {
        "module": str(alice.module.id),
        "topic": str(alice.topic.id),
        "assessment": str(alice.assessment.id),
        "task": str(alice.task.id),
        "session": str(alice.study_session.id),
    }
    missing = {key: str(uuid.uuid4()) for key in hers}
    return {**hers, **mine}, {**missing, **mine}


async def snapshot(api: AsyncClient, rows: Rows) -> tuple[Any, ...]:
    """Everything a user owns, as their own client sees it."""
    return (
        (await api.get("/modules")).json(),
        (await api.get(f"/modules/{rows.module.id}/topics")).json(),
        (await api.get("/assessments")).json(),
        (await api.get("/tasks")).json(),
        (await api.get(f"/modules/{rows.module.id}/sessions")).json(),
        (await api.get(f"/sessions/{rows.study_session.id}")).json(),
        (await api.get("/sessions/active")).json(),
    )


@pytest.mark.parametrize(("method", "path", "body"), ATTEMPTS)
async def test_bob_gets_the_same_404_as_for_a_missing_id(
    alice_api: AsyncClient,
    bob_api: AsyncClient,
    alice: Rows,
    bob: Rows,
    method: str,
    path: str,
    body: dict[str, Any] | None,
) -> None:
    before = (await snapshot(alice_api, alice), await snapshot(bob_api, bob))
    hers, missing = ids_of(alice, bob)

    attempt = await bob_api.request(method, fill(path, hers), json=fill(body, hers))
    baseline = await bob_api.request(method, fill(path, missing), json=fill(body, missing))

    assert attempt.status_code == 404
    assert (attempt.status_code, attempt.json()) == (baseline.status_code, baseline.json())
    # Neither Alice's data nor Bob's changed (a rejected write leaves nothing behind).
    assert (await snapshot(alice_api, alice), await snapshot(bob_api, bob)) == before


@pytest.mark.parametrize(
    "path",
    [
        "/assessments",
        "/assessments?status=upcoming",
        "/tasks",
        "/tasks?status=todo&status=in_progress",
    ],
)
async def test_cross_module_lists_hold_only_your_own_rows(
    alice_api: AsyncClient, bob_api: AsyncClient, alice: Rows, bob: Rows, path: str
) -> None:
    def ids(rows: list[dict[str, Any]]) -> set[str]:
        return {row["id"] for row in rows}

    his = ids((await bob_api.get(path)).json())
    hers = ids((await alice_api.get(path)).json())

    assert his == {str(bob.assessment.id)} or his == {str(bob.task.id)}
    assert hers == {str(alice.assessment.id)} or hers == {str(alice.task.id)}


async def test_lists_never_include_the_other_users_modules(
    alice_api: AsyncClient, bob_api: AsyncClient, alice: Rows, bob: Rows
) -> None:
    assert [m["id"] for m in (await alice_api.get("/modules")).json()] == [str(alice.module.id)]
    assert [m["id"] for m in (await bob_api.get("/modules")).json()] == [str(bob.module.id)]


async def test_same_code_is_fine_across_users(bob_api: AsyncClient, alice: Rows) -> None:
    # Alice already has COS330; Bob creating his own must not conflict or leak.
    response = await bob_api.post("/modules", json={"code": "COS330", "name": "Bob's"})
    assert response.status_code == 201


async def test_bob_never_sees_alices_open_session(
    alice_api: AsyncClient, bob_api: AsyncClient, alice: Rows, bob: Rows
) -> None:
    start = {"id": str(uuid.uuid4()), "occurred_at": "2026-11-01T08:00:00Z"}
    body = {"module_id": str(alice.module.id), "start": start}
    hers = (await alice_api.post("/sessions", json=body)).json()["id"]

    assert (await bob_api.get("/sessions/active")).json() is None
    history = (await bob_api.get(f"/modules/{bob.module.id}/sessions")).json()
    assert [s["id"] for s in history] == [str(bob.study_session.id)]
    # Her open session doesn't stop him starting one.
    mine = await bob_api.post("/sessions", json={"module_id": str(bob.module.id), "start": start})
    assert mine.status_code == 201
    assert mine.json()["id"] != hers


async def test_reusing_alices_event_id_neither_fails_nor_leaks(
    bob_api: AsyncClient, alice: Rows, bob: Rows
) -> None:
    # Event ids are unique per user, so a collision can't reveal that hers exists.
    start = {"id": str(alice.start_event_id), "occurred_at": "2026-11-01T08:00:00Z"}

    response = await bob_api.post(
        "/sessions", json={"module_id": str(bob.module.id), "start": start}
    )

    assert response.status_code == 201
    assert response.json()["events"][0]["id"] == str(alice.start_event_id)
