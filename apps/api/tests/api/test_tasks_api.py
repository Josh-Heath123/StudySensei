from typing import Any

from httpx import AsyncClient


async def module_and_assignment(api: AsyncClient) -> tuple[str, str]:
    module = (await api.post("/modules", json={"code": "COS330", "name": "Architecture"})).json()
    exam = (
        await api.post(
            f"/modules/{module['id']}/assessments", json={"title": "A1", "kind": "assignment"}
        )
    ).json()
    return module["id"], exam["id"]


async def create(api: AsyncClient, module_id: str, **body: Any) -> dict[str, Any]:
    response = await api.post(f"/modules/{module_id}/tasks", json={"title": "Task", **body})
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


async def test_task_crud_and_status(alice_api: AsyncClient) -> None:
    module, assignment = await module_and_assignment(alice_api)
    task = await create(
        alice_api,
        module,
        title="Draft report",
        assessment_id=assignment,
        due_at="2026-11-25T21:59:00Z",
    )
    assert (task["status"], task["completed_at"], task["assessment_id"]) == (
        "todo",
        None,
        assignment,
    )
    url = f"/tasks/{task['id']}"

    started = (await alice_api.patch(url, json={"status": "in_progress"})).json()
    assert (started["status"], started["completed_at"]) == ("in_progress", None)

    done = (await alice_api.patch(url, json={"status": "done"})).json()
    assert done["completed_at"] is not None

    reopened = (await alice_api.patch(url, json={"status": "todo"})).json()
    assert reopened["completed_at"] is None

    unlinked = (await alice_api.patch(url, json={"assessment_id": None, "notes": "solo"})).json()
    assert (unlinked["assessment_id"], unlinked["notes"]) == (None, "solo")

    assert (await alice_api.delete(url)).status_code == 204
    assert (await alice_api.get(url)).status_code == 404


async def test_filters_and_order(alice_api: AsyncClient) -> None:
    module, assignment = await module_and_assignment(alice_api)
    await create(alice_api, module, title="Undated")
    await create(
        alice_api, module, title="Later", due_at="2026-12-01T10:00:00Z", assessment_id=assignment
    )
    await create(alice_api, module, title="Sooner", due_at="2026-11-20T10:00:00Z")

    def titles(response: Any) -> list[str]:
        return [t["title"] for t in response.json()]

    assert titles(await alice_api.get(f"/tasks?module_id={module}")) == [
        "Sooner",
        "Later",
        "Undated",
    ]
    assert titles(await alice_api.get(f"/tasks?assessment_id={assignment}")) == ["Later"]


async def test_invalid_tasks_are_422(alice_api: AsyncClient) -> None:
    module, _ = await module_and_assignment(alice_api)
    other = (await alice_api.post("/modules", json={"code": "COS301", "name": "Other"})).json()
    foreign = await alice_api.post(
        f"/modules/{other['id']}/assessments", json={"title": "B", "kind": "exam"}
    )
    foreign_assessment = foreign.json()["id"]

    response = await alice_api.post(
        f"/modules/{module}/tasks", json={"title": "X", "assessment_id": foreign_assessment}
    )
    assert response.status_code == 422
    assert "same module" in response.json()["detail"]

    task = await create(alice_api, module)
    for body in ({"title": None}, {"status": None}, {"status": "blocked"}):
        assert (await alice_api.patch(f"/tasks/{task['id']}", json=body)).status_code == 422, body
