from typing import Any

from httpx import AsyncClient


async def new_module(api: AsyncClient) -> str:
    response = await api.post("/modules", json={"code": "COS330", "name": "Architecture"})
    module_id: str = response.json()["id"]
    return module_id


async def add(api: AsyncClient, module_id: str, name: str, parent: str | None = None) -> str:
    response = await api.post(
        f"/modules/{module_id}/topics", json={"name": name, "parent_id": parent}
    )
    assert response.status_code == 201, response.text
    topic_id: str = response.json()["id"]
    return topic_id


def shape(nodes: list[dict[str, Any]]) -> list[Any]:
    return [(n["name"], shape(n["children"])) if n["children"] else n["name"] for n in nodes]


async def tree(api: AsyncClient, module_id: str) -> list[Any]:
    response = await api.get(f"/modules/{module_id}/topics")
    assert response.status_code == 200
    return shape(response.json())


async def test_build_rename_move_and_delete(alice_api: AsyncClient) -> None:
    module = await new_module(alice_api)
    patterns = await add(alice_api, module, "Patterns")
    creational = await add(alice_api, module, "Creational", patterns)
    await add(alice_api, module, "Factory", creational)
    queues = await add(alice_api, module, "Queues")
    assert await tree(alice_api, module) == [("Patterns", [("Creational", ["Factory"])]), "Queues"]

    renamed = await alice_api.patch(f"/topics/{queues}", json={"name": "Message queues"})
    assert (renamed.status_code, renamed.json()["name"]) == (200, "Message queues")

    # Indent "Message queues" under Patterns, after Creational.
    moved = await alice_api.post(
        f"/topics/{queues}/move", json={"parent_id": patterns, "position": 1}
    )
    assert moved.status_code == 200
    assert await tree(alice_api, module) == [
        ("Patterns", [("Creational", ["Factory"]), "Message queues"])
    ]

    # Outdent Creational to the top level, first.
    await alice_api.post(f"/topics/{creational}/move", json={"parent_id": None, "position": 0})
    assert await tree(alice_api, module) == [
        ("Creational", ["Factory"]),
        ("Patterns", ["Message queues"]),
    ]

    assert (await alice_api.delete(f"/topics/{creational}")).status_code == 204
    assert await tree(alice_api, module) == [("Patterns", ["Message queues"])]


async def test_cannot_move_into_own_subtree(alice_api: AsyncClient) -> None:
    module = await new_module(alice_api)
    parent = await add(alice_api, module, "Parent")
    child = await add(alice_api, module, "Child", parent)

    response = await alice_api.post(
        f"/topics/{parent}/move", json={"parent_id": child, "position": 0}
    )

    assert response.status_code == 422
    assert "under itself" in response.json()["detail"]


async def test_explicit_null_name_is_422(alice_api: AsyncClient) -> None:
    module = await new_module(alice_api)
    topic = await add(alice_api, module, "Topic")

    response = await alice_api.patch(f"/topics/{topic}", json={"name": None})

    assert response.status_code == 422
    assert "name cannot be null" in response.text
    cleared = await alice_api.patch(f"/topics/{topic}", json={"description": None})
    assert cleared.status_code == 200
