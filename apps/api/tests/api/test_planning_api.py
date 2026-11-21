"""Planning endpoints: settings, weekly rules, exceptions, expanded availability, and a
topic's workload and confidence."""

import hashlib
import uuid
from dataclasses import replace
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk, ChunkTopic, Material, MaterialPage, Topic
from app.models.materials import EMBEDDING_DIMENSIONS
from tests.academics.conftest import Rows

# --- settings --------------------------------------------------------------------------


async def test_settings_default_to_johannesburg_and_three_hours(alice_api: AsyncClient) -> None:
    response = await alice_api.get("/planning/settings")

    assert response.json() == {
        "timezone": "Africa/Johannesburg",
        "daily_study_cap_minutes": 180,
        "reminder_minutes": 10,
    }


async def test_settings_change_and_are_validated(alice_api: AsyncClient) -> None:
    changed = await alice_api.patch(
        "/planning/settings", json={"timezone": "Europe/London", "daily_study_cap_minutes": 240}
    )
    assert changed.json() == {
        "timezone": "Europe/London",
        "daily_study_cap_minutes": 240,
        "reminder_minutes": 10,
    }

    for body in (
        {"timezone": "Mars/Olympus"},
        {"timezone": "GMT+2 "},
        {"daily_study_cap_minutes": 10},
        {"daily_study_cap_minutes": 1441},
        {"timezone": None},
    ):
        assert (await alice_api.patch("/planning/settings", json=body)).status_code == 422, body


# --- rules -----------------------------------------------------------------------------


async def rule(api: AsyncClient, weekday: int, start: str, end: str) -> Any:
    return await api.post(
        "/availability/rules", json={"weekday": weekday, "start": start, "end": end}
    )


async def test_rules_are_created_listed_in_order_and_deleted(alice_api: AsyncClient) -> None:
    late = (await rule(alice_api, 0, "20:00", "24:00")).json()
    await rule(alice_api, 0, "18:00", "19:30")
    await rule(alice_api, 6, "09:00", "10:00")

    listed = (await alice_api.get("/availability/rules")).json()
    assert [(r["weekday"], r["start"], r["end"]) for r in listed] == [
        (0, "18:00", "19:30"),
        (0, "20:00", "24:00"),
        (6, "09:00", "10:00"),
    ]
    assert (await alice_api.delete(f"/availability/rules/{late['id']}")).status_code == 204
    assert len((await alice_api.get("/availability/rules")).json()) == 2


async def test_overlapping_rules_conflict_but_touching_ones_are_fine(
    alice_api: AsyncClient,
) -> None:
    await rule(alice_api, 2, "09:00", "12:00")

    overlap = await rule(alice_api, 2, "11:00", "13:00")
    touching = await rule(alice_api, 2, "12:00", "13:00")
    other_day = await rule(alice_api, 3, "11:00", "13:00")

    assert (overlap.status_code, overlap.json()["detail"]) == (
        409,
        "That window overlaps another on Wednesday.",
    )
    assert touching.status_code == 201
    assert other_day.status_code == 201


@pytest.mark.parametrize(
    "body",
    [
        {"weekday": 7, "start": "09:00", "end": "10:00"},
        {"weekday": 0, "start": "10:00", "end": "09:00"},
        {"weekday": 0, "start": "10:00", "end": "10:00"},
        {"weekday": 0, "start": "23:00", "end": "01:00"},  # crosses midnight: split it
        {"weekday": 0, "start": "9:00", "end": "10:00"},
        {"weekday": 0, "start": "09:00", "end": "24:30"},
        {"weekday": 0, "start": "09:00"},
    ],
)
async def test_bad_rules_are_refused(alice_api: AsyncClient, body: dict[str, Any]) -> None:
    assert (await alice_api.post("/availability/rules", json=body)).status_code == 422


async def test_a_rule_is_updated_and_checked_again(alice_api: AsyncClient) -> None:
    first = (await rule(alice_api, 1, "09:00", "10:00")).json()
    await rule(alice_api, 1, "11:00", "12:00")

    moved = await alice_api.patch(f"/availability/rules/{first['id']}", json={"end": "10:30"})
    backwards = await alice_api.patch(f"/availability/rules/{first['id']}", json={"start": "11:00"})
    into = await alice_api.patch(f"/availability/rules/{first['id']}", json={"end": "11:30"})

    assert moved.json()["end"] == "10:30"
    assert backwards.status_code == 422
    assert into.status_code == 409
    listed = (await alice_api.get("/availability/rules")).json()
    assert [(r["start"], r["end"]) for r in listed] == [("09:00", "10:30"), ("11:00", "12:00")]


# --- exceptions ------------------------------------------------------------------------


async def test_exceptions_one_per_date(alice_api: AsyncClient) -> None:
    off = await alice_api.post(
        "/availability/exceptions",
        json={"date": "2026-11-27", "unavailable": True, "note": "Graduation"},
    )
    again = await alice_api.post(
        "/availability/exceptions",
        json={"date": "2026-11-27", "windows": [{"start": "08:00", "end": "09:00"}]},
    )

    assert off.status_code == 201
    assert off.json() | {"id": None} == {
        "id": None,
        "date": "2026-11-27",
        "unavailable": True,
        "windows": [],
        "note": "Graduation",
    }
    assert (again.status_code, again.json()["detail"]) == (
        409,
        "2026-11-27 already has an exception.",
    )


async def test_an_exceptions_windows_are_sorted_and_validated(alice_api: AsyncClient) -> None:
    made = await alice_api.post(
        "/availability/exceptions",
        json={
            "date": "2026-11-28",
            "windows": [{"start": "14:00", "end": "16:00"}, {"start": "08:00", "end": "10:00"}],
        },
    )
    assert made.json()["windows"] == [
        {"start": "08:00", "end": "10:00"},
        {"start": "14:00", "end": "16:00"},
    ]

    for body in (
        {"date": "2026-11-29"},  # neither
        {
            "date": "2026-11-29",
            "unavailable": True,
            "windows": [{"start": "08:00", "end": "09:00"}],
        },
        {
            "date": "2026-11-29",
            "windows": [{"start": "08:00", "end": "10:00"}, {"start": "09:00", "end": "11:00"}],
        },
        {"date": "2026-11-29", "windows": [{"start": "22:00", "end": "02:00"}]},
    ):
        assert (await alice_api.post("/availability/exceptions", json=body)).status_code == 422


async def test_an_exception_switches_between_unavailable_and_windows(
    alice_api: AsyncClient,
) -> None:
    made = (
        await alice_api.post(
            "/availability/exceptions",
            json={"date": "2026-11-30", "windows": [{"start": "08:00", "end": "09:00"}]},
        )
    ).json()
    url = f"/availability/exceptions/{made['id']}"

    off = await alice_api.patch(url, json={"unavailable": True})
    assert (off.json()["unavailable"], off.json()["windows"]) == (True, [])
    no_windows = await alice_api.patch(url, json={"unavailable": False})
    assert no_windows.status_code == 422
    back = await alice_api.patch(
        url, json={"unavailable": False, "windows": [{"start": "10:00", "end": "11:00"}]}
    )
    assert back.json()["windows"] == [{"start": "10:00", "end": "11:00"}]
    assert (await alice_api.delete(url)).status_code == 204


async def test_exceptions_can_be_listed_for_a_range(alice_api: AsyncClient) -> None:
    for day in ("2026-12-01", "2026-12-05", "2026-12-10"):
        await alice_api.post("/availability/exceptions", json={"date": day, "unavailable": True})

    listed = await alice_api.get(
        "/availability/exceptions", params={"from": "2026-12-02", "to": "2026-12-10"}
    )

    assert [e["date"] for e in listed.json()] == ["2026-12-05", "2026-12-10"]


# --- expanded availability -------------------------------------------------------------


async def test_the_week_expands_rules_and_exceptions_with_the_cap(alice_api: AsyncClient) -> None:
    await rule(alice_api, 0, "08:00", "12:00")  # Monday: 4 h, capped at 3 h
    await rule(alice_api, 1, "18:00", "20:00")  # Tuesday: 2 h, but an exception…
    await alice_api.post(
        "/availability/exceptions",
        json={"date": "2026-11-17", "windows": [{"start": "09:00", "end": "09:30"}]},
    )
    await alice_api.post(
        "/availability/exceptions", json={"date": "2026-11-18", "unavailable": True}
    )

    week = (
        await alice_api.get("/availability", params={"from": "2026-11-16", "to": "2026-11-22"})
    ).json()

    assert week["timezone"] == "Africa/Johannesburg"
    monday, tuesday, wednesday = week["days"][:3]
    assert monday["intervals"] == [
        {"start": "2026-11-16T06:00:00Z", "end": "2026-11-16T10:00:00Z", "minutes": 240}
    ]
    assert (monday["source"], monday["free_minutes"], monday["available_minutes"]) == (
        "rules",
        240,
        180,
    )
    assert (tuesday["source"], tuesday["free_minutes"]) == ("exception", 30)
    assert (wednesday["source"], wednesday["intervals"]) == ("unavailable", [])
    assert [d["weekday"] for d in week["days"]] == [0, 1, 2, 3, 4, 5, 6]
    assert week["total_free_minutes"] == 270
    assert week["total_available_minutes"] == 210
    assert week["weekly_minutes_from_rules"] == 180 + 120


async def test_the_users_timezone_and_cap_are_used(alice_api: AsyncClient) -> None:
    await rule(alice_api, 6, "00:30", "03:00")
    await alice_api.patch(
        "/planning/settings", json={"timezone": "Europe/London", "daily_study_cap_minutes": 600}
    )

    spring = (
        await alice_api.get("/availability", params={"from": "2026-03-29", "to": "2026-03-29"})
    ).json()

    assert spring["days"][0]["free_minutes"] == 90  # the clocks went forward


@pytest.mark.parametrize(
    "params",
    [
        {"from": "2026-11-20", "to": "2026-11-19"},
        {"from": "2026-11-01", "to": "2027-01-02"},
        {"from": "2026-11-01"},
        {"from": "yesterday", "to": "2026-11-19"},
    ],
)
async def test_bad_ranges_are_refused(alice_api: AsyncClient, params: dict[str, str]) -> None:
    assert (await alice_api.get("/availability", params=params)).status_code == 422


# --- a topic's workload and confidence -------------------------------------------------


async def link_pages(session: AsyncSession, rows: Rows, kind: str, pages: int) -> None:
    """``pages`` pages of a material of ``kind``, each with a chunk linked to the topic."""
    material = Material(
        user_id=rows.user.id,
        module_id=rows.module.id,
        kind=kind,
        title=kind,
        original_filename=f"{kind}.pdf",
        content_type="application/pdf",
        size_bytes=10,
        sha256=hashlib.sha256(kind.encode()).hexdigest(),
        status="ready",
        allow_ai=False,
    )
    session.add(material)
    await session.flush()
    for number in range(1, pages + 1):
        session.add(
            MaterialPage(
                user_id=rows.user.id,
                material_id=material.id,
                page_number=number,
                text="Text",
                char_count=4,
                is_scanned=False,
            )
        )
        await session.flush()
        # Two chunks on a page still count it once.
        for position in (0, 1):
            chunk = Chunk(
                user_id=rows.user.id,
                module_id=rows.module.id,
                material_id=material.id,
                page_number=number,
                position=position,
                text="Text",
                token_count=1,
                embedding=[0.0] * EMBEDDING_DIMENSIONS,
            )
            session.add(chunk)
            await session.flush()
            session.add(
                ChunkTopic(
                    chunk_id=chunk.id,
                    topic_id=rows.topic.id,
                    module_id=rows.module.id,
                    method="pages",
                    score=1.0,
                )
            )
    await session.commit()


async def tree_topic(api: AsyncClient, rows: Rows) -> Any:
    tree = (await api.get(f"/modules/{rows.module.id}/topics")).json()
    return next(t for t in tree if t["id"] == str(rows.topic.id))


async def test_the_workload_is_estimated_from_slides_and_text_pages(
    alice_api: AsyncClient, session: AsyncSession, alice: Rows
) -> None:
    assert (await tree_topic(alice_api, alice))["workload"] == {
        "minutes": None,
        "source": "none",
        "slide_pages": 0,
        "text_pages": 0,
    }
    await link_pages(session, alice, "slides", 18)
    await link_pages(session, alice, "notes", 2)
    await link_pages(session, alice, "past_paper", 5)  # practice: not counted

    topic = await tree_topic(alice_api, alice)

    assert topic["workload"] == {
        "minutes": 70,  # 18 x 3 + 2 x 6 = 66, rounded up to 5
        "source": "estimated",
        "slide_pages": 18,
        "text_pages": 2,
    }
    assert topic["confidence"] is None


async def test_the_students_own_figure_and_confidence_are_kept(
    alice_api: AsyncClient, session: AsyncSession, alice: Rows
) -> None:
    await link_pages(session, alice, "slides", 10)
    url = f"/topics/{alice.topic.id}/planning"

    set_both = await alice_api.patch(url, json={"estimated_minutes": 120, "confidence": 2})
    assert set_both.json() == {
        "topic_id": str(alice.topic.id),
        "confidence": 2,
        "workload": {"minutes": 120, "source": "yours", "slide_pages": 10, "text_pages": 0},
    }
    topic = await tree_topic(alice_api, alice)
    assert (topic["confidence"], topic["workload"]["source"]) == (2, "yours")

    cleared = await alice_api.patch(url, json={"estimated_minutes": None, "confidence": None})
    assert cleared.json()["confidence"] is None
    assert cleared.json()["workload"] == {
        "minutes": 30,
        "source": "estimated",
        "slide_pages": 10,
        "text_pages": 0,
    }


@pytest.mark.parametrize(
    "body",
    [
        {"confidence": 0},
        {"confidence": 6},
        {"estimated_minutes": 4},
        {"estimated_minutes": 6001},
        {"name": "Not here"},
    ],
)
async def test_bad_planning_values_are_refused(
    alice_api: AsyncClient, alice: Rows, body: dict[str, Any]
) -> None:
    response = await alice_api.patch(f"/topics/{alice.topic.id}/planning", json=body)
    assert response.status_code == 422


async def test_a_topic_with_subtopics_also_has_its_whole_workload(
    alice_api: AsyncClient, session: AsyncSession, alice: Rows
) -> None:
    child = (
        await alice_api.post(
            f"/modules/{alice.module.id}/topics",
            json={"name": "Sagas", "parent_id": str(alice.topic.id)},
        )
    ).json()
    await link_pages(session, alice, "slides", 4)
    sagas = await session.get(Topic, uuid.UUID(child["id"]))
    assert sagas is not None
    await link_pages(session, replace(alice, topic=sagas), "notes", 2)

    topic = await tree_topic(alice_api, alice)

    assert topic["workload"]["minutes"] == 15  # its own 4 slides
    # Decision 0019: the figure the planner uses when the chapter is ticked.
    assert topic["workload_with_subtopics"] == {
        "minutes": 25,  # 4 x 3 + 2 x 6 = 24, rounded up to 5
        "source": "estimated",
        "slide_pages": 4,
        "text_pages": 2,
        "subtopics": 1,
    }
    assert topic["children"][0]["workload_with_subtopics"] is None
    # The student's figure on the chapter covers the whole chapter.
    await alice_api.patch(f"/topics/{alice.topic.id}/planning", json={"estimated_minutes": 300})
    topic = await tree_topic(alice_api, alice)
    assert topic["workload_with_subtopics"]["minutes"] == 300
    assert topic["workload_with_subtopics"]["source"] == "yours"
