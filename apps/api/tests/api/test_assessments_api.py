from typing import Any

from httpx import AsyncClient

EXAM_DATE = "2026-11-28T07:00:00Z"


async def module_with_topics(api: AsyncClient) -> tuple[str, list[str]]:
    module = (await api.post("/modules", json={"code": "COS330", "name": "Architecture"})).json()
    topics = [
        (await api.post(f"/modules/{module['id']}/topics", json={"name": name})).json()["id"]
        for name in ("Patterns", "Queues", "Microservices")
    ]
    return module["id"], topics


async def create(api: AsyncClient, module_id: str, **body: Any) -> dict[str, Any]:
    response = await api.post(
        f"/modules/{module_id}/assessments", json={"title": "Exam", "kind": "exam", **body}
    )
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


async def test_assessment_crud_with_topics(alice_api: AsyncClient) -> None:
    module, (patterns, queues, micro) = await module_with_topics(alice_api)

    exam = await create(
        alice_api, module, due_at=EXAM_DATE, weight=50, topic_ids=[patterns, queues]
    )
    assert exam["weight"] == 50.0  # a number, not "50.00"
    assert exam["due_at"].startswith("2026-11-28T07:00:00")
    assert sorted(exam["topic_ids"]) == sorted([patterns, queues])
    url = f"/assessments/{exam['id']}"

    patched = (await alice_api.patch(url, json={"topic_ids": [micro], "weight": 40})).json()
    assert (patched["topic_ids"], patched["weight"], patched["title"]) == ([micro], 40.0, "Exam")

    cleared = (await alice_api.patch(url, json={"due_at": None, "topic_ids": []})).json()
    assert (cleared["due_at"], cleared["topic_ids"]) == (None, [])

    assert (await alice_api.delete(url)).status_code == 204
    assert (await alice_api.get(url)).status_code == 404


def titles(response: Any) -> list[str]:
    assert response.status_code == 200, response.text
    return [a["title"] for a in response.json()]


async def test_module_list_is_sorted_and_scoped(alice_api: AsyncClient) -> None:
    module, _ = await module_with_topics(alice_api)
    other = (await alice_api.post("/modules", json={"code": "COS301", "name": "Other"})).json()
    await create(alice_api, module, title="Undated")
    await create(alice_api, module, title="Later", due_at="2026-12-01T07:00:00Z")
    await create(alice_api, module, title="Sooner", due_at="2026-11-20T07:00:00Z")
    await create(alice_api, other["id"], title="Elsewhere")

    assert titles(await alice_api.get(f"/modules/{module}/assessments")) == [
        "Sooner",
        "Later",
        "Undated",
    ]
    assert titles(await alice_api.get(f"/modules/{other['id']}/assessments")) == ["Elsewhere"]


async def test_cross_module_list_filters_by_status(alice_api: AsyncClient) -> None:
    module, _ = await module_with_topics(alice_api)
    other = (await alice_api.post("/modules", json={"code": "COS301", "name": "Other"})).json()
    await create(alice_api, module, title="Exam", due_at="2026-11-28T07:00:00Z")
    await create(alice_api, other["id"], title="Essay", due_at="2026-11-20T07:00:00Z")
    await create(alice_api, other["id"], title="Old test", status="completed")
    await create(alice_api, module, title="Dropped quiz", status="cancelled")

    assert titles(await alice_api.get("/assessments?status=upcoming")) == ["Essay", "Exam"]
    assert titles(await alice_api.get("/assessments?status=completed&status=cancelled")) == [
        "Dropped quiz",
        "Old test",
    ]
    assert len(titles(await alice_api.get("/assessments"))) == 4
    assert (await alice_api.get("/assessments?status=nope")).status_code == 422


async def test_invalid_assessments_are_422(alice_api: AsyncClient) -> None:
    module, _ = await module_with_topics(alice_api)
    url = f"/modules/{module}/assessments"
    bad = [
        {"title": "X", "kind": "exam", "weight": 101},
        {"title": "X", "kind": "exam", "weight": -1},
        {"title": "X", "kind": "essay"},
        {"title": "X", "kind": "exam", "due_at": "2026-11-28T09:00:00"},  # no timezone
    ]
    for body in bad:
        assert (await alice_api.post(url, json=body)).status_code == 422, body

    exam = await create(alice_api, module)
    for body in ({"title": None}, {"topic_ids": None}, {"kind": None}):
        response = await alice_api.patch(f"/assessments/{exam['id']}", json=body)
        assert response.status_code == 422, body


async def test_topic_from_another_module_is_422_and_changes_nothing(
    alice_api: AsyncClient,
) -> None:
    module, (patterns, *_) = await module_with_topics(alice_api)
    other = (await alice_api.post("/modules", json={"code": "COS301", "name": "Other"})).json()
    foreign = (
        await alice_api.post(f"/modules/{other['id']}/topics", json={"name": "Foreign"})
    ).json()["id"]
    exam = await create(alice_api, module, topic_ids=[patterns])

    response = await alice_api.patch(
        f"/assessments/{exam['id']}", json={"title": "Renamed", "topic_ids": [foreign]}
    )

    assert response.status_code == 422
    after = (await alice_api.get(f"/assessments/{exam['id']}")).json()
    assert (after["title"], after["topic_ids"]) == ("Exam", [patterns])


async def test_deleting_an_assessment_keeps_its_tasks(alice_api: AsyncClient) -> None:
    module, _ = await module_with_topics(alice_api)
    exam = await create(alice_api, module)
    task = (
        await alice_api.post(
            f"/modules/{module}/tasks", json={"title": "Revise", "assessment_id": exam["id"]}
        )
    ).json()

    await alice_api.delete(f"/assessments/{exam['id']}")

    kept = (await alice_api.get(f"/tasks/{task['id']}")).json()
    assert (kept["title"], kept["assessment_id"]) == ("Revise", None)
