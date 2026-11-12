"""Over HTTP, Bob can't reach Alice's modules or topics.

Every request Bob makes with one of Alice's IDs must get exactly the response
a random, non-existent ID gets, so he can't even tell her rows exist. Afterwards
Alice's data must be unchanged.
"""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient

from tests.academics.conftest import Rows

# (method, path template, body). {module}/{topic} are filled with Alice's IDs,
# or with random UUIDs for the baseline. {my_topic} is always one of Bob's.
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
]


def fill(value: Any, ids: dict[str, str]) -> Any:
    if isinstance(value, str):
        return value.format(**ids)
    if isinstance(value, dict):
        return {k: fill(v, ids) for k, v in value.items()}
    return value


async def snapshot(api: AsyncClient, rows: Rows) -> tuple[Any, Any]:
    module = (await api.get(f"/modules/{rows.module.id}")).json()
    tree = (await api.get(f"/modules/{rows.module.id}/topics")).json()
    return module, tree


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
    before = await snapshot(alice_api, alice)
    hers = {
        "module": str(alice.module.id),
        "topic": str(alice.topic.id),
        "my_topic": str(bob.topic.id),
    }
    missing = {**hers, "module": str(uuid.uuid4()), "topic": str(uuid.uuid4())}

    attempt = await bob_api.request(method, fill(path, hers), json=fill(body, hers))
    baseline = await bob_api.request(method, fill(path, missing), json=fill(body, missing))

    assert attempt.status_code == 404
    assert (attempt.status_code, attempt.json()) == (baseline.status_code, baseline.json())
    assert await snapshot(alice_api, alice) == before


async def test_lists_never_include_the_other_users_modules(
    alice_api: AsyncClient, bob_api: AsyncClient, alice: Rows, bob: Rows
) -> None:
    assert [m["id"] for m in (await alice_api.get("/modules")).json()] == [str(alice.module.id)]
    assert [m["id"] for m in (await bob_api.get("/modules")).json()] == [str(bob.module.id)]


async def test_same_code_is_fine_across_users(bob_api: AsyncClient, alice: Rows) -> None:
    # Alice already has COS330; Bob creating his own must not conflict or leak.
    response = await bob_api.post("/modules", json={"code": "COS330", "name": "Bob's"})
    assert response.status_code == 201
