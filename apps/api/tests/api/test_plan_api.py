"""The stored plan over HTTP (decision 0021): GET /plan creates version 1, the next block,
skipping, re-planning on request, and sessions for a planned block."""

import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient

from tests.academics.conftest import Rows


@pytest.fixture
async def planned(alice_api: AsyncClient, alice: Rows) -> Rows:
    """Evenings free every day, and her test in 6 days on a topic of 5 h."""
    for weekday in range(7):
        await alice_api.post(
            "/availability/rules", json={"weekday": weekday, "start": "18:00", "end": "21:00"}
        )
    due = (datetime.now(UTC) + timedelta(days=6)).isoformat()
    await alice_api.patch(f"/assessments/{alice.assessment.id}", json={"due_at": due})
    await alice_api.patch(f"/topics/{alice.topic.id}/planning", json={"estimated_minutes": 300})
    return alice


async def test_get_plan_creates_version_1_once(alice_api: AsyncClient, planned: Rows) -> None:
    first = await alice_api.get("/plan")
    assert first.status_code == 200
    body = first.json()
    assert (body["number"], body["trigger"], body["summary"]) == (1, "initial", "Your first plan.")
    assert body["timezone"] == "Africa/Johannesburg"
    assert body["report"]["overall"]["line"]
    assert body["blocks"]
    for block in body["blocks"]:
        assert block["status"] == "planned" and block["fixed"] is False
        assert block["module_code"] == "COS330"
        assert block["reason_text"] and block["method_text"]
    # Asking again doesn't make another version.
    assert (await alice_api.get("/plan")).json()["number"] == 1
    # A longer range holds at least as many blocks.
    later = (datetime.now(UTC) + timedelta(days=10)).date().isoformat()
    wide = await alice_api.get("/plan", params={"to": later})
    assert len(wide.json()["blocks"]) >= len(body["blocks"])


async def test_next_skip_and_replan(alice_api: AsyncClient, planned: Rows) -> None:
    assert (await alice_api.get("/plan/next")).json() is None  # no plan yet
    await alice_api.get("/plan")
    upcoming = (await alice_api.get("/plan/next")).json()
    assert upcoming["status"] == "planned"

    skipped = await alice_api.post(f"/plan/blocks/{upcoming['id']}/skip")
    assert skipped.status_code == 200
    version = skipped.json()
    assert (version["number"], version["trigger"]) == (2, "skip")
    assert version["summary"].startswith("You skipped Microservices (")
    assert version["summary"].endswith("): its time is placed again.")
    # Only a planned block of the current plan: now it's skipped (and on version 1).
    again = await alice_api.post(f"/plan/blocks/{upcoming['id']}/skip")
    assert again.status_code == 409
    assert (await alice_api.post(f"/plan/blocks/{uuid.uuid4()}/skip")).status_code == 404

    replanned = (await alice_api.post("/plan/replan")).json()
    assert replanned["number"] == 2  # nothing changed: no new version
    assert (await alice_api.get("/plan/next")).json()["id"] != upcoming["id"]


async def test_a_session_for_a_planned_block(alice_api: AsyncClient, planned: Rows) -> None:
    await alice_api.get("/plan")
    block = (await alice_api.get("/plan/next")).json()
    start = {"id": str(uuid.uuid4()), "occurred_at": datetime.now(UTC).isoformat()}

    other_topic = (
        await alice_api.post(f"/modules/{planned.module.id}/topics", json={"name": "Other"})
    ).json()
    wrong = await alice_api.post(
        "/sessions",
        json={
            "module_id": str(planned.module.id),
            "topic_id": other_topic["id"],
            "plan_block_id": block["id"],
            "start": start,
        },
    )
    assert wrong.status_code == 422

    ok = await alice_api.post(
        "/sessions",
        json={
            "module_id": str(planned.module.id),
            "topic_id": str(planned.topic.id),
            "plan_block_id": block["id"],
            "start": start,
        },
    )
    assert ok.status_code == 201
    assert ok.json()["plan_block_id"] == block["id"]


@pytest.mark.parametrize(
    "params",
    [{"from": "2026-12-10", "to": "2026-12-01"}, {"from": "2026-01-01", "to": "2026-12-31"}],
)
async def test_bad_ranges_are_refused(
    alice_api: AsyncClient, planned: Rows, params: dict[str, str]
) -> None:
    assert (await alice_api.get("/plan", params=params)).status_code == 422


async def test_move_a_block(alice_api: AsyncClient, planned: Rows) -> None:
    plan = (await alice_api.get("/plan")).json()
    movable = [b for b in plan["blocks"] if b["actions"]["move"] and b["kind"] == "study"]
    assert movable
    block = movable[-1]
    tz = ZoneInfo("Africa/Johannesburg")
    tomorrow = datetime.now(tz).date() + timedelta(days=1)

    # Not on the grid: refused by the schema.
    odd = datetime.combine(tomorrow, time(18, 3), tzinfo=tz).isoformat()
    assert (
        await alice_api.post(f"/plan/blocks/{block['id']}/move", json={"start": odd})
    ).status_code == 422
    # Outside study time: one sentence.
    morning = datetime.combine(tomorrow, time(10, 0), tzinfo=tz).isoformat()
    refused = await alice_api.post(f"/plan/blocks/{block['id']}/move", json={"start": morning})
    assert refused.status_code == 422
    assert refused.json() == {
        "detail": f"That's outside your study time on {tomorrow:%a} {tomorrow.day} {tomorrow:%b}."
    }
    # Somewhere free: the first evening slot the server accepts.
    for day in range(1, 5):
        for minutes in range(0, 135, 5):
            start = datetime.combine(
                tomorrow + timedelta(days=day - 1), time(18), tzinfo=tz
            ) + timedelta(minutes=minutes)
            moved = await alice_api.post(
                f"/plan/blocks/{block['id']}/move", json={"start": start.isoformat()}
            )
            if moved.status_code == 200:
                version = moved.json()
                assert version["trigger"] == "move"
                assert version["summary"].startswith("You moved Microservices from ")
                after = (
                    await alice_api.get(
                        "/plan", params={"to": (tomorrow + timedelta(days=6)).isoformat()}
                    )
                ).json()
                pinned = [b for b in after["blocks"] if b["pinned"]]
                assert [datetime.fromisoformat(b["start"]) for b in pinned] == [start]
                # The old row is on the old version: moving it again is a conflict.
                again = await alice_api.post(
                    f"/plan/blocks/{block['id']}/move", json={"start": start.isoformat()}
                )
                assert again.status_code == 409
                return
            assert moved.status_code == 422
    raise AssertionError("no free slot accepted")


async def test_a_block_done_early_shows_at_its_measured_time(
    alice_api: AsyncClient, planned: Rows
) -> None:
    """Decision 0023: started from Next up hours before its slot and ended, a done block is
    shown when it was studied, with the plan's times as planned_start and planned_end, and
    its old slot (which the finish re-plan may use again) holds at most one block."""
    await alice_api.get("/plan")
    block = (await alice_api.get("/plan/next")).json()
    assert block["planned_start"] == block["start"] and block["planned_end"] == block["end"]
    began = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=50)
    ended = began + timedelta(minutes=48)
    study = (
        await alice_api.post(
            "/sessions",
            json={
                "module_id": str(planned.module.id),
                "topic_id": str(planned.topic.id),
                "plan_block_id": block["id"],
                "start": {"id": str(uuid.uuid4()), "occurred_at": began.isoformat()},
            },
        )
    ).json()
    end = {"id": str(uuid.uuid4()), "type": "end", "occurred_at": ended.isoformat()}
    assert (
        await alice_api.post(f"/sessions/{study['id']}/events", json={"events": [end]})
    ).status_code == 200
    await alice_api.post("/plan/replan")  # the finish re-plan, inline

    tz = ZoneInfo("Africa/Johannesburg")
    first = min(began.astimezone(tz).date(), datetime.fromisoformat(block["start"]).date())
    last = first + timedelta(days=8)
    blocks = (
        await alice_api.get("/plan", params={"from": first.isoformat(), "to": last.isoformat()})
    ).json()["blocks"]
    done = next(b for b in blocks if b["id"] == block["id"])
    assert done["status"] == "done"
    assert datetime.fromisoformat(done["start"]) == began
    assert datetime.fromisoformat(done["end"]) == ended
    assert done["minutes"] == 48
    assert (done["planned_start"], done["planned_end"]) == (block["start"], block["end"])
    # Its old slot: never the done block and a planned one on top of each other.
    slot = (datetime.fromisoformat(block["start"]), datetime.fromisoformat(block["end"]))
    in_slot = [
        b
        for b in blocks
        if datetime.fromisoformat(b["start"]) < slot[1]
        and datetime.fromisoformat(b["end"]) > slot[0]
    ]
    assert done not in in_slot
    assert len(in_slot) <= 1

    # A range holding only the session's day still returns it; one holding only the old
    # slot's day doesn't.
    day = began.astimezone(tz).date().isoformat()
    on_day = (await alice_api.get("/plan", params={"from": day, "to": day})).json()["blocks"]
    assert block["id"] in {b["id"] for b in on_day}
    slot_day = slot[0].astimezone(tz).date()
    if slot_day != began.astimezone(tz).date():
        there = (
            await alice_api.get(
                "/plan", params={"from": slot_day.isoformat(), "to": slot_day.isoformat()}
            )
        ).json()["blocks"]
        assert block["id"] not in {b["id"] for b in there}
