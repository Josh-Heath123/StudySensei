"""The index_material job: chunks a material's pages, embeds them, then marks it ready."""

from pathlib import Path

import pytest
from sqlalchemy import delete, func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs import queue
from app.jobs.kinds import INDEX_MATERIAL
from app.models import Chunk, Job, Material, MaterialPage
from app.services import materials as materials_service
from app.storage.local import LocalStorage
from tests.academics.conftest import Rows
from tests.fakes import FakeEmbedder
from tests.search.conftest import Page, add_material, run_jobs

FIXTURES = Path(__file__).parents[1] / "fixtures"


async def chunks_of(session: AsyncSession, material: Material) -> list[Chunk]:
    # By identity: the worker's rollbacks expire the test's objects.
    material_id = inspect(material).identity[0]  # type: ignore[index]
    result = await session.scalars(
        select(Chunk)
        .where(Chunk.material_id == material_id)
        .order_by(Chunk.page_number, Chunk.position)
        .execution_options(populate_existing=True)
    )
    return list(result)


async def test_each_page_becomes_chunks_and_the_material_is_ready(
    session: AsyncSession, alice: Rows, tmp_path: Path, fake_embedder: FakeEmbedder
) -> None:
    user_id, module_id = alice.user.id, alice.module.id
    paragraph = " ".join(f"w{i}" for i in range(199)) + "."  # 200 tokens
    material = await add_material(
        session,
        alice.user,
        alice.module,
        "CH03",
        [
            Page("Passwords are salted and hashed.", title="User authentication"),
            Page("", scanned=True),
            Page("\n\n".join([paragraph] * 3)),  # 600 tokens: more than one chunk
        ],
    )

    # index_material, then (decision 0006) extract_topics, which fails with no AI key in
    # tests, and the merge that relinks without it.
    assert await run_jobs(session, tmp_path) == 3

    chunks = await chunks_of(session, material)
    assert {c.page_number for c in chunks} == {1, 3}  # the scanned page is skipped
    assert [c.position for c in chunks if c.page_number == 3] == [0, 1]
    first = chunks[0]
    assert (first.page_number, first.position) == (1, 0)
    assert (first.text, first.token_count) == ("Passwords are salted and hashed.", 6)
    assert (first.user_id, first.module_id) == (user_id, module_id)
    assert len(first.embedding) == 384
    assert all(c.token_count <= 400 for c in chunks)
    # The embedded text leads with the material and page titles; the stored text doesn't.
    assert fake_embedder.passages[0] == (
        "CH03 · User authentication\n\nPasswords are salted and hashed."
    )
    assert fake_embedder.passages[1].startswith("CH03\n\nw0 w1 ")
    assert fake_embedder.passage_calls == [len(chunks)]  # one batched call

    await session.refresh(material)
    assert (material.status, material.error) == ("ready", None)


async def test_the_keyword_index_is_generated_from_the_text(
    session: AsyncSession, alice: Rows, tmp_path: Path
) -> None:
    user_id = alice.user.id
    await add_material(session, alice.user, alice.module, "M", [Page("Salting passwords")])
    await run_jobs(session, tmp_path)
    tsv = await session.scalar(select(Chunk.tsv).where(Chunk.user_id == user_id))
    assert tsv == "'password':2 'salt':1"


async def test_a_material_with_only_scanned_pages_is_ready_with_no_chunks(
    session: AsyncSession, alice: Rows, tmp_path: Path
) -> None:
    pages = [Page("", scanned=True), Page("ab", scanned=True)]
    material = await add_material(session, alice.user, alice.module, "Scan", pages)
    await run_jobs(session, tmp_path)
    assert await chunks_of(session, material) == []
    await session.refresh(material)
    assert material.status == "ready"


async def test_running_again_replaces_the_chunks(
    session: AsyncSession, alice: Rows, tmp_path: Path
) -> None:
    user_id = alice.user.id
    material = await add_material(session, alice.user, alice.module, "M", [Page("First version")])
    material_id = material.id
    await run_jobs(session, tmp_path)
    before = await chunks_of(session, material)

    page = await session.scalar(select(MaterialPage).where(MaterialPage.material_id == material_id))
    assert page is not None
    page.text, page.char_count = "Second version", len("Second version")
    queue.enqueue(session, INDEX_MATERIAL, {"material_id": str(material_id)}, user_id=user_id)
    await session.commit()
    await run_jobs(session, tmp_path)

    after = await chunks_of(session, material)
    assert [c.text for c in after] == ["Second version"]
    assert {c.id for c in after}.isdisjoint({c.id for c in before})


async def test_replacing_pages_on_re_extraction_removes_their_chunks(
    session: AsyncSession, alice: Rows, tmp_path: Path
) -> None:
    material = await add_material(session, alice.user, alice.module, "M", [Page("Old text")])
    material_id = material.id
    await run_jobs(session, tmp_path)
    assert len(await chunks_of(session, material)) == 1

    # What extract_text does before writing the new pages.
    await session.execute(delete(MaterialPage).where(MaterialPage.material_id == material_id))
    await session.commit()
    assert await chunks_of(session, material) == []


async def test_deleting_a_material_deletes_its_chunks_and_pending_index_job(
    session: AsyncSession, alice: Rows, tmp_path: Path
) -> None:
    user_id = alice.user.id
    done = await add_material(session, alice.user, alice.module, "Done", [Page("Indexed text")])
    done_id = done.id
    await run_jobs(session, tmp_path)
    await session.refresh(alice.user)
    await session.refresh(alice.module)
    waiting = await add_material(session, alice.user, alice.module, "Waiting", [Page("Not yet")])
    storage = LocalStorage(tmp_path / "storage")

    await materials_service.delete_material(session, storage, done_id, user_id=user_id)
    await materials_service.delete_material(session, storage, waiting.id, user_id=user_id)

    assert await session.scalar(select(func.count()).select_from(Chunk)) == 0
    queued = select(func.count()).select_from(Job).where(Job.status == "queued")
    assert await session.scalar(queued) == 0


async def test_another_users_material_id_in_a_job_does_nothing(
    session: AsyncSession, alice: Rows, bob: Rows, tmp_path: Path
) -> None:
    hers = await add_material(
        session, alice.user, alice.module, "Hers", [Page("Private")], queue_index=False
    )
    queue.enqueue(session, INDEX_MATERIAL, {"material_id": str(hers.id)}, user_id=bob.user.id)
    await session.commit()

    await run_jobs(session, tmp_path)

    assert await chunks_of(session, hers) == []
    await session.refresh(hers)
    assert hers.status == "processing"


async def test_an_embedding_failure_is_retried_with_a_readable_reason(
    session: AsyncSession,
    alice: Rows,
    tmp_path: Path,
    fake_embedder: FakeEmbedder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    material = await add_material(session, alice.user, alice.module, "M", [Page("Some text")])

    def broken(texts: object) -> list[list[float]]:
        raise RuntimeError("onnx exploded")

    monkeypatch.setattr(fake_embedder, "embed_passages", broken)
    await run_jobs(session, tmp_path)  # one attempt; the retry isn't due yet

    await session.refresh(material)
    assert material.status == "processing"
    assert material.error is not None and "retried" in material.error
    assert "onnx" not in material.error  # the internal error isn't shown to the student
    assert await chunks_of(session, material) == []


async def test_an_upload_is_extracted_then_indexed_then_ready(
    session: AsyncSession, alice: Rows, tmp_path: Path
) -> None:
    storage = LocalStorage(tmp_path / "storage")
    with (FIXTURES / "slides.pptx").open("rb") as source:
        material = await materials_service.upload_material(
            session,
            storage,
            alice.module.id,
            user_id=alice.user.id,
            source=source,
            filename="slides.pptx",
            kind="slides",
            title=None,
            allow_ai=False,  # local embedding runs regardless
            max_bytes=10_000_000,
        )

    # extract_text, index_material, then link_topics (AI is off, so no topic extraction)
    assert await run_jobs(session, tmp_path) == 3
    await session.refresh(material)
    assert material.status == "ready"
    chunks = await chunks_of(session, material)
    assert chunks
    assert {c.page_number for c in chunks} <= {1, 2}  # slide 3 is a picture only
