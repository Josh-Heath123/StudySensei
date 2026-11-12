from httpx import AsyncClient


async def create(api: AsyncClient, code: str = "COS330", **extra: object) -> dict[str, object]:
    response = await api.post("/modules", json={"code": code, "name": "Architecture", **extra})
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


async def test_module_crud(alice_api: AsyncClient) -> None:
    module = await create(alice_api, code=" cos330 ", semester="2026-S2", colour="#5856D6")
    assert (module["code"], module["semester"], module["colour"]) == (
        "COS330",
        "2026-S2",
        "#5856D6",
    )
    url = f"/modules/{module['id']}"

    assert [m["id"] for m in (await alice_api.get("/modules")).json()] == [module["id"]]
    assert (await alice_api.get(url)).json()["name"] == "Architecture"

    patched = await alice_api.patch(url, json={"name": "Software Architecture"})
    assert patched.status_code == 200
    assert patched.json()["name"] == "Software Architecture"
    assert patched.json()["semester"] == "2026-S2"  # untouched

    cleared = await alice_api.patch(url, json={"semester": None})
    assert (cleared.status_code, cleared.json()["semester"]) == (200, None)

    assert (await alice_api.delete(url)).status_code == 204
    assert (await alice_api.get(url)).status_code == 404


async def test_duplicate_code_is_409_on_create_and_update(alice_api: AsyncClient) -> None:
    await create(alice_api, code="COS330")
    other = await create(alice_api, code="COS301")

    for response in (
        await alice_api.post("/modules", json={"code": "cos330", "name": "Again"}),
        await alice_api.patch(f"/modules/{other['id']}", json={"code": "Cos330"}),
    ):
        assert response.status_code == 409
        assert response.json() == {"detail": "You already have a module with the code COS330."}

    # The failed request left nothing half-done.
    codes = [m["code"] for m in (await alice_api.get("/modules")).json()]
    assert codes == ["COS301", "COS330"]


async def test_explicit_null_for_required_field_is_422(alice_api: AsyncClient) -> None:
    url = f"/modules/{(await create(alice_api))['id']}"

    for field in ("name", "code", "colour"):
        response = await alice_api.patch(url, json={field: None})
        assert response.status_code == 422, field
        assert f"{field} cannot be null" in response.text

    assert (await alice_api.get(url)).json()["name"] == "Architecture"


async def test_invalid_input_is_422(alice_api: AsyncClient) -> None:
    bad_bodies = [
        {"code": "COS330", "name": "X", "colour": "blue"},
        {"code": "", "name": "X"},
        {"code": "COS330", "name": "X", "owner": "someone-else"},  # unknown field
        {"name": "No code"},
    ]
    for body in bad_bodies:
        assert (await alice_api.post("/modules", json=body)).status_code == 422, body
