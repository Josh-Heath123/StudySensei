"""Push and calendar endpoints over HTTP (decision 0024)."""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from icalendar import Calendar

from app.services.push.sender import FakePushSender
from tests.academics.conftest import Rows

SUB = {
    "endpoint": "https://push.example/edge",
    "keys": {"p256dh": "BKey-1_x", "auth": "Auth_1"},
    "label": "Edge on Windows",
}


async def test_config_disabled_without_keys(alice_api: AsyncClient) -> None:
    assert (await alice_api.get("/push/config")).json() == {"enabled": False, "public_key": None}
    test = await alice_api.post("/push/test")
    assert test.status_code == 409
    assert test.json()["detail"] == "Reminders aren't set up on the server yet."


async def test_config_with_keys(alice_api: AsyncClient, push_on: FakePushSender) -> None:
    assert (await alice_api.get("/push/config")).json() == {
        "enabled": True,
        "public_key": "BPublicKeyForTests",
    }


async def test_subscribe_list_test_and_remove(
    alice_api: AsyncClient, alice: Rows, push_on: FakePushSender
) -> None:
    created = await alice_api.post("/push/subscriptions", json=SUB)
    assert created.status_code == 201
    device = created.json()
    assert set(device) == {"id", "label", "created_at", "last_success_at"}  # no endpoint
    again = await alice_api.post("/push/subscriptions", json={**SUB, "label": "Edge (new)"})
    assert again.status_code == 200 and again.json()["id"] == device["id"]

    listed = (await alice_api.get("/push/subscriptions")).json()
    assert [(d["id"], d["label"]) for d in listed] == [(device["id"], "Edge (new)")]

    sent = (await alice_api.post("/push/test")).json()
    assert sent == {"devices": [{"id": device["id"], "label": "Edge (new)", "outcome": "sent"}]}
    assert push_on.sent[0][1]["title"] == "Reminders work"
    assert (await alice_api.get("/push/subscriptions")).json()[0]["last_success_at"]

    push_on.statuses["https://push.example/edge"] = 410
    gone = (await alice_api.post("/push/test")).json()["devices"]
    assert gone[0]["outcome"] == "removed"
    assert (await alice_api.get("/push/subscriptions")).json() == []

    await alice_api.post("/push/subscriptions", json=SUB)
    row = (await alice_api.get("/push/subscriptions")).json()[0]
    assert (await alice_api.delete(f"/push/subscriptions/{row['id']}")).status_code == 204
    assert (await alice_api.delete(f"/push/subscriptions/{row['id']}")).status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {**SUB, "endpoint": "http://push.example/edge"},
        {**SUB, "endpoint": "not a url"},
        {**SUB, "keys": {"p256dh": "has spaces", "auth": "a"}},
        {**SUB, "label": ""},
        {**SUB, "extra": 1},
    ],
)
async def test_bad_subscriptions_are_refused(
    alice_api: AsyncClient, alice: Rows, body: dict[str, object]
) -> None:
    assert (await alice_api.post("/push/subscriptions", json=body)).status_code == 422


@pytest.mark.parametrize("minutes", [None, 5, 10, 15, 30])
async def test_reminder_minutes(alice_api: AsyncClient, alice: Rows, minutes: int | None) -> None:
    response = await alice_api.patch("/planning/settings", json={"reminder_minutes": minutes})
    assert response.status_code == 200
    assert response.json()["reminder_minutes"] == minutes
    assert (await alice_api.get("/planning/settings")).json()["reminder_minutes"] == minutes


@pytest.mark.parametrize("minutes", [0, 1, 20, 60, "10"])
async def test_other_reminder_minutes_are_refused(
    alice_api: AsyncClient, alice: Rows, minutes: object
) -> None:
    response = await alice_api.patch("/planning/settings", json={"reminder_minutes": minutes})
    assert response.status_code == 422


async def test_calendar_feed_create_fetch_reset_delete(alice_api: AsyncClient, alice: Rows) -> None:
    assert (await alice_api.get("/calendar/feed")).json() == {
        "exists": False,
        "created_at": None,
        "last_fetched_at": None,
    }
    created = await alice_api.post("/calendar/feed")
    assert created.status_code == 201
    url = created.json()["url"]
    assert url.startswith("http://localhost:5173/api/calendar/") and url.endswith(".ics")
    token = url.rsplit("/", 1)[-1].removesuffix(".ics")
    assert len(token) >= 43
    state = (await alice_api.get("/calendar/feed")).json()
    assert state["exists"] is True and state["last_fetched_at"] is None
    assert token not in str(state)

    served = await alice_api.get(f"/calendar/{token}.ics")
    assert served.status_code == 200
    assert served.headers["content-type"] == "text/calendar; charset=utf-8"
    assert served.headers["cache-control"] == "private, max-age=300"
    cal = Calendar.from_ical(served.content)
    assert cal["X-WR-CALNAME"] == "StudySensei plan"
    fetched = (await alice_api.get("/calendar/feed")).json()["last_fetched_at"]
    assert fetched is not None
    assert datetime.fromisoformat(fetched) <= datetime.now(UTC)

    # A reset kills the old token.
    new_url = (await alice_api.post("/calendar/feed")).json()["url"]
    assert new_url != url
    assert (await alice_api.get(f"/calendar/{token}.ics")).status_code == 404
    new_token = new_url.rsplit("/", 1)[-1].removesuffix(".ics")
    assert (await alice_api.get(f"/calendar/{new_token}.ics")).status_code == 200

    assert (await alice_api.delete("/calendar/feed")).status_code == 204
    assert (await alice_api.get(f"/calendar/{new_token}.ics")).status_code == 404
    assert (await alice_api.delete("/calendar/feed")).status_code == 404


async def test_unknown_tokens_are_404(alice_api: AsyncClient, alice: Rows) -> None:
    for token in ("nope", uuid.uuid4().hex, "a" * 43):
        assert (await alice_api.get(f"/calendar/{token}.ics")).status_code == 404


async def test_download(alice_api: AsyncClient, alice: Rows) -> None:
    response = await alice_api.get("/calendar/plan.ics")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/calendar; charset=utf-8"
    assert 'filename="studysensei.ics"' in response.headers["content-disposition"]
    assert b"BEGIN:VCALENDAR" in response.content
