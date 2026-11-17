"""Material endpoints: upload validation, dedupe, edit, delete and retry."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.jobs.worker import run_once
from app.models import Job, Material
from app.storage.base import blob_key
from app.storage.local import LocalStorage
from tests.academics.conftest import Rows
from tests.materials import samples

FIXTURES = Path(__file__).parents[1] / "fixtures"

PPTX_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


async def upload(
    api: AsyncClient,
    module_id: uuid.UUID | str,
    filename: str = "Week 3 slides.pdf",
    data: bytes | None = None,
    **form: Any,
) -> Response:
    fields = {
        "kind": "slides",
        **{k: str(v).lower() if isinstance(v, bool) else v for k, v in form.items()},
    }
    return await api.post(
        f"/modules/{module_id}/materials",
        files={"file": (filename, data if data is not None else samples.pdf(3))},
        data=fields,
    )


async def test_upload_stores_the_file_and_queues_processing(
    alice_api: AsyncClient, alice: Rows, session: AsyncSession, storage: LocalStorage
) -> None:
    data = samples.pptx(4)
    response = await upload(alice_api, alice.module.id, "Week_3 - Layers.pptx", data)

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Week 3 - Layers"  # from the filename when none is given
    assert body["original_filename"] == "Week_3 - Layers.pptx"
    assert body["content_type"] == PPTX_TYPE
    assert body["size_bytes"] == len(data)
    assert (body["status"], body["page_count"], body["error"]) == ("uploaded", None, None)
    assert (body["allow_ai"], body["retrying"]) == (True, False)

    with storage.open(blob_key(alice.user.id, body["sha256"])) as f:
        assert f.read() == data
    jobs = list(await session.scalars(select(Job).where(Job.user_id == alice.user.id)))
    assert [(j.kind, j.payload, j.status) for j in jobs] == [
        ("extract_text", {"material_id": body["id"]}, "queued")
    ]


async def test_upload_takes_a_title_kind_and_ai_flag(alice_api: AsyncClient, alice: Rows) -> None:
    response = await upload(
        alice_api,
        alice.module.id,
        "u_submission.docx",
        samples.docx(),
        kind="assignment",
        title="  My assignment 1  ",
        allow_ai=False,
    )

    assert response.status_code == 201
    body = response.json()
    assert (body["kind"], body["title"], body["allow_ai"]) == (
        "assignment",
        "My assignment 1",
        False,
    )


async def test_a_client_path_in_the_filename_is_dropped(
    alice_api: AsyncClient, alice: Rows
) -> None:
    response = await upload(alice_api, alice.module.id, "C:\\Users\\me\\..\\notes.txt", samples.TXT)

    assert response.status_code == 201
    assert response.json()["original_filename"] == "notes.txt"


@pytest.mark.parametrize(
    ("filename", "data", "status", "detail"),
    [
        ("setup.exe", b"MZ\x90\x00", 415, ".exe can't be uploaded"),
        ("slides.pdf", samples.PNG, 415, "doesn't look like PDF"),
        ("empty.pdf", b"", 422, "The file is empty."),
    ],
)
async def test_bad_files_are_refused_and_nothing_is_kept(
    alice_api: AsyncClient,
    alice: Rows,
    session: AsyncSession,
    storage: LocalStorage,
    filename: str,
    data: bytes,
    status: int,
    detail: str,
) -> None:
    response = await upload(alice_api, alice.module.id, filename, data)

    assert response.status_code == status
    assert detail in response.json()["detail"]
    assert await session.scalar(select(Material.id)) is None
    assert not storage.root.exists() or not any(storage.root.rglob("*"))


async def test_files_over_the_limit_are_413(
    alice_api: AsyncClient, alice: Rows, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 2 * 1024 * 1024)
    big = b"%PDF-" + b"0" * (2 * 1024 * 1024)

    response = await upload(alice_api, alice.module.id, "big.pdf", big)

    assert response.status_code == 413
    assert response.json()["detail"] == "Files can be at most 2 MB."


async def test_a_file_just_over_the_limit_is_caught_while_reading(
    alice_api: AsyncClient, alice: Rows, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Under the Content-Length allowance (form overhead), so only the byte count catches it.
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 1024 * 1024)
    response = await upload(alice_api, alice.module.id, "big.pdf", b"%PDF-" + b"0" * 1024 * 1024)

    assert response.status_code == 413


async def test_bad_form_fields_are_422(alice_api: AsyncClient, alice: Rows) -> None:
    assert (await upload(alice_api, alice.module.id, kind="lecture")).status_code == 422
    assert (await upload(alice_api, alice.module.id, title="x" * 201)).status_code == 422
    missing_kind = await alice_api.post(
        f"/modules/{alice.module.id}/materials", files={"file": ("a.pdf", samples.pdf())}
    )
    assert missing_kind.status_code == 422


async def test_the_same_file_twice_in_a_module_is_a_409(
    alice_api: AsyncClient, alice: Rows, storage: LocalStorage
) -> None:
    data = samples.pdf(2)
    first = await upload(alice_api, alice.module.id, "Week 3.pdf", data, title="Week 3 slides")
    again = await upload(alice_api, alice.module.id, "copy of week 3.pdf", data)

    assert (first.status_code, again.status_code) == (201, 409)
    assert again.json()["detail"] == "This file is already in the module as “Week 3 slides”."
    assert len(list(storage.root.rglob("*.part"))) == 0
    assert len([p for p in storage.root.rglob("*") if p.is_file()]) == 1


async def test_another_module_shares_the_stored_file_until_the_last_copy_goes(
    alice_api: AsyncClient, alice: Rows, storage: LocalStorage
) -> None:
    other = (await alice_api.post("/modules", json={"code": "COS301", "name": "Other"})).json()
    data = samples.pdf(2)
    a = (await upload(alice_api, alice.module.id, "shared.pdf", data)).json()
    b = await upload(alice_api, other["id"], "shared.pdf", data)
    assert b.status_code == 201
    key = blob_key(alice.user.id, a["sha256"])
    assert len([p for p in storage.root.rglob("*") if p.is_file()]) == 1

    assert (await alice_api.delete(f"/materials/{a['id']}")).status_code == 204
    assert storage.exists(key)  # still used by the other module

    assert (await alice_api.delete(f"/materials/{b.json()['id']}")).status_code == 204
    assert not storage.exists(key)


async def test_deleting_a_module_deletes_its_files(
    alice_api: AsyncClient, alice: Rows, storage: LocalStorage, session: AsyncSession
) -> None:
    material = (await upload(alice_api, alice.module.id)).json()

    assert (await alice_api.delete(f"/modules/{alice.module.id}")).status_code == 204

    assert not storage.exists(blob_key(alice.user.id, material["sha256"]))
    assert await session.scalar(select(Job.id).where(Job.user_id == alice.user.id)) is None


async def test_list_get_and_update(
    alice_api: AsyncClient, alice: Rows, session: AsyncSession
) -> None:
    older = (await upload(alice_api, alice.module.id, "a.txt", samples.TXT)).json()
    newer = (await upload(alice_api, alice.module.id, "b.md", samples.MD)).json()
    # Every row in a test transaction gets the same now(); make the first one older.
    await session.execute(
        update(Material)
        .where(Material.id == uuid.UUID(older["id"]))
        .values(created_at=func.now() - timedelta(hours=1))
    )
    await session.commit()
    older = (await alice_api.get(f"/materials/{older['id']}")).json()

    listed = (await alice_api.get(f"/modules/{alice.module.id}/materials")).json()
    assert [m["id"] for m in listed] == [newer["id"], older["id"]]
    assert (await alice_api.get(f"/materials/{older['id']}")).json() == older

    changed = await alice_api.patch(
        f"/materials/{older['id']}",
        json={"title": "Week 1 notes", "kind": "notes", "allow_ai": False},
    )
    assert changed.status_code == 200
    assert (changed.json()["title"], changed.json()["kind"], changed.json()["allow_ai"]) == (
        "Week 1 notes",
        "notes",
        False,
    )
    assert (
        await alice_api.patch(f"/materials/{older['id']}", json={"title": None})
    ).status_code == 422
    assert (
        await alice_api.patch(f"/materials/{older['id']}", json={"kind": "lecture"})
    ).status_code == 422


async def test_only_a_failed_material_can_be_retried(
    alice_api: AsyncClient, alice: Rows, session: AsyncSession
) -> None:
    material = (await upload(alice_api, alice.module.id)).json()
    path = f"/materials/{material['id']}/retry"
    assert (await alice_api.post(path)).status_code == 422

    row = await session.get(Material, uuid.UUID(material["id"]))
    assert row is not None
    row.status, row.error = "failed", "The PDF couldn't be read."
    await session.commit()

    retried = await alice_api.post(path)
    assert retried.status_code == 200
    assert (retried.json()["status"], retried.json()["error"]) == ("uploaded", None)
    jobs = await session.scalars(select(Job.kind).where(Job.user_id == alice.user.id))
    assert list(jobs) == ["extract_text", "extract_text"]


async def test_the_worker_makes_an_upload_ready(
    alice_api: AsyncClient, alice: Rows, session: AsyncSession, storage: LocalStorage
) -> None:
    deck = (FIXTURES / "slides.pptx").read_bytes()
    material = (await upload(alice_api, alice.module.id, "deck.pptx", deck)).json()

    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        yield session

    # Later than the test transaction's now(), which stamped the job's run_after.
    later = datetime.now(UTC) + timedelta(hours=1)
    assert await run_once(sessions, storage, now=lambda: later)  # extract_text

    # Extracted but not yet searchable: still processing.
    got = (await alice_api.get(f"/materials/{material['id']}")).json()
    assert (got["status"], got["page_count"], got["scanned_page_count"]) == ("processing", 3, 1)

    assert await run_once(sessions, storage, now=lambda: later)  # index_material
    # Then its topic jobs (decision 0006): with no AI key in tests, extraction fails and
    # the merge just relinks. None of it changes the material.
    ran = 0
    while await run_once(sessions, storage, now=lambda: later):
        ran += 1
    assert ran == 2  # extract_topics, merge_topics

    got = (await alice_api.get(f"/materials/{material['id']}")).json()
    assert (got["status"], got["page_count"], got["error"], got["retrying"]) == (
        "ready",
        3,
        None,
        False,
    )
    assert got["scanned_page_count"] == 1  # the picture-only slide


async def process(session: AsyncSession, storage: LocalStorage) -> None:
    """Run the worker until the queue is empty."""

    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        yield session

    later = datetime.now(UTC) + timedelta(hours=1)
    while await run_once(sessions, storage, now=lambda: later):
        pass


async def test_extracted_pages_can_be_listed_and_read(
    alice_api: AsyncClient, alice: Rows, session: AsyncSession, storage: LocalStorage
) -> None:
    pdf = (FIXTURES / "lecture.pdf").read_bytes()
    material = (await upload(alice_api, alice.module.id, "lecture.pdf", pdf)).json()
    path = f"/materials/{material['id']}/pages"
    assert (await alice_api.get(path)).json() == []  # not extracted yet

    await process(session, storage)

    got = (await alice_api.get(f"/materials/{material['id']}")).json()
    assert (got["status"], got["page_count"], got["scanned_page_count"]) == ("ready", 3, 1)
    pages = (await alice_api.get(path)).json()
    assert [(p["page_number"], p["is_scanned"]) for p in pages] == [
        (1, False),
        (2, True),
        (3, False),
    ]
    assert "text" not in pages[0]
    first = (await alice_api.get(f"{path}/1")).json()
    assert first["text"].startswith("Week 3: Layered architecture\n")
    assert first["char_count"] == len(first["text"])
    assert (await alice_api.get(f"{path}/2")).json()["text"] == ""
    assert (await alice_api.get(f"{path}/4")).status_code == 404
    assert (await alice_api.get(f"{path}/0")).status_code == 422


async def test_extracting_again_replaces_the_pages(
    alice_api: AsyncClient, alice: Rows, session: AsyncSession, storage: LocalStorage
) -> None:
    deck = (FIXTURES / "slides.pptx").read_bytes()
    material = (await upload(alice_api, alice.module.id, "slides.pptx", deck)).json()
    await process(session, storage)
    row = await session.get(Material, uuid.UUID(material["id"]))
    assert row is not None
    row.status = "failed"
    await session.commit()

    assert (await alice_api.post(f"/materials/{material['id']}/retry")).status_code == 200
    await process(session, storage)

    pages = (await alice_api.get(f"/materials/{material['id']}/pages")).json()
    assert [(p["page_number"], p["title"]) for p in pages] == [
        (1, "Architectural styles"),
        (2, "Quality attributes"),
        (3, None),
    ]


async def test_a_password_protected_pdf_fails_with_a_readable_reason(
    alice_api: AsyncClient, alice: Rows, session: AsyncSession, storage: LocalStorage
) -> None:
    pdf = (FIXTURES / "protected.pdf").read_bytes()
    material = (await upload(alice_api, alice.module.id, "locked.pdf", pdf)).json()

    await process(session, storage)

    got = (await alice_api.get(f"/materials/{material['id']}")).json()
    assert (got["status"], got["retrying"]) == ("failed", False)
    assert got["error"] == "The PDF is password-protected. Remove the password and upload it again."
    assert (await alice_api.get(f"/materials/{material['id']}/pages")).json() == []
