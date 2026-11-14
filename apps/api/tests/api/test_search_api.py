"""GET /modules/{id}/search over HTTP: uploads processed by the worker, then searched."""

from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.local import LocalStorage
from tests.academics.conftest import Rows
from tests.api.test_materials_api import FIXTURES, process, upload


async def test_nothing_indexed_yet(alice_api: AsyncClient, alice: Rows) -> None:
    response = await alice_api.get(f"/modules/{alice.module.id}/search", params={"q": "anything"})
    assert response.status_code == 200
    assert response.json() == {"query": "anything", "results": [], "indexed_chunks": 0}


async def test_uploaded_slides_can_be_searched(
    alice_api: AsyncClient, alice: Rows, session: AsyncSession, storage: LocalStorage
) -> None:
    module_id = alice.module.id
    deck = (FIXTURES / "slides.pptx").read_bytes()
    material = (await upload(alice_api, module_id, "deck.pptx", deck)).json()
    await process(session, storage)

    pages = (await alice_api.get(f"/materials/{material['id']}/pages")).json()
    page = (await alice_api.get(f"/materials/{material['id']}/pages/2")).json()
    phrase = " ".join(page["text"].split()[:4])

    response = await alice_api.get(f"/modules/{module_id}/search", params={"q": phrase, "limit": 2})
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    assert body["query"] == phrase
    assert body["indexed_chunks"] >= 2
    assert len(body["results"]) <= 2
    top = body["results"][0]
    assert top["material_id"] == material["id"]
    assert top["material_title"] == material["title"]
    assert top["original_filename"] == "deck.pptx"
    assert top["page_number"] == 2
    assert top["page_title"] == pages[1]["title"]
    assert top["keyword_rank"] == 1
    assert top["score"] > 0
    assert any(part["highlight"] for part in top["snippet"])
    assert set(top) == {
        "chunk_id",
        "material_id",
        "material_title",
        "original_filename",
        "page_number",
        "page_title",
        "position",
        "text",
        "snippet",
        "score",
        "vector_rank",
        "keyword_rank",
    }


async def test_query_validation(alice_api: AsyncClient, alice: Rows) -> None:
    path = f"/modules/{alice.module.id}/search"
    assert (await alice_api.get(path)).status_code == 422
    assert (await alice_api.get(path, params={"q": ""})).status_code == 422
    assert (await alice_api.get(path, params={"q": "x" * 501})).status_code == 422
    assert (await alice_api.get(path, params={"q": "x", "limit": 0})).status_code == 422
    assert (await alice_api.get(path, params={"q": "x", "limit": 21})).status_code == 422


async def test_bob_never_finds_alices_material_in_his_own_module(
    alice_api: AsyncClient,
    bob_api: AsyncClient,
    alice: Rows,
    bob: Rows,
    session: AsyncSession,
    storage: LocalStorage,
) -> None:
    bob_module = bob.module.id
    deck = (FIXTURES / "slides.pptx").read_bytes()
    await upload(alice_api, alice.module.id, "deck.pptx", deck)
    await process(session, storage)

    response = await bob_api.get(f"/modules/{bob_module}/search", params={"q": "slide"})
    assert response.json() == {"query": "slide", "results": [], "indexed_chunks": 0}
