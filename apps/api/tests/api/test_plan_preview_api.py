"""GET /plan/preview: the plan computed on request, with its text and feasibility report."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import StudySession
from tests.academics.conftest import Rows


async def evenings(api: AsyncClient) -> None:
    for weekday in range(7):
        response = await api.post(
            "/availability/rules", json={"weekday": weekday, "start": "18:00", "end": "21:00"}
        )
        assert response.status_code == 201


async def test_the_preview_has_blocks_with_text_and_a_report(
    alice_api: AsyncClient, alice: Rows, session: AsyncSession
) -> None:
    await evenings(alice_api)
    due = (datetime.now(UTC) + timedelta(days=6)).isoformat()
    await alice_api.patch(f"/assessments/{alice.assessment.id}", json={"due_at": due, "weight": 30})
    await alice_api.patch(f"/topics/{alice.topic.id}/planning", json={"estimated_minutes": 200})
    sessions_before = await session.scalar(select(func.count()).select_from(StudySession))

    response = await alice_api.get("/plan/preview", params={"days": 7})

    assert response.status_code == 200
    body = response.json()
    assert (body["timezone"], body["days"], body["daily_study_cap_minutes"]) == (
        "Africa/Johannesburg",
        7,
        180,
    )
    blocks = body["blocks"]
    assert {b["kind"] for b in blocks} == {"study", "review"}
    for block in blocks:
        assert block["module_code"] == "COS330"
        assert block["assessment_title"] == "Semester test 1"
        assert block["reason_text"] and block["method_text"]
        if block["kind"] == "review":
            assert (block["topic_id"], block["topic_name"], block["method"]) == (
                None,
                None,
                "mixed_review",
            )
        else:
            assert block["topic_name"] == "Microservices"
    # 200 min by her own figure, less the 50 measured: 150 to plan.
    study = [b for b in blocks if b["kind"] == "study"]
    assert sum(b["minutes"] for b in study) >= 150
    labelled = "3 h 20 by your own figure; 50 min studied so far (measured, 1 session)."
    assert any(labelled in b["reason_text"] for b in study)

    report = body["feasibility"]
    entry = report["assessments"][0]
    assert (entry["required_minutes"], entry["status"]) == (150, "fits")
    assert entry["topics"][0]["topic_name"] == "Microservices"
    assert report["overall"]["line"].startswith("You need 2 h 30 before ")
    assert report["levers"] == []
    assert report["basis"]
    # Nothing was stored.
    assert await session.scalar(select(func.count()).select_from(StudySession)) == sessions_before


async def test_with_nothing_due_the_preview_is_empty(alice_api: AsyncClient) -> None:
    body = (await alice_api.get("/plan/preview")).json()
    assert body["days"] == 28
    assert body["blocks"] == []
    assert body["feasibility"]["overall"]["line"] == "Nothing is due in the next 28 days."
    assert body["feasibility"]["overall"]["deadline"] is None


@pytest.mark.parametrize("days", ["0", "63", "x"])
async def test_bad_windows_are_refused(alice_api: AsyncClient, days: str) -> None:
    assert (await alice_api.get("/plan/preview", params={"days": days})).status_code == 422
