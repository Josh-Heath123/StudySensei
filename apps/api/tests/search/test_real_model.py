"""Smoke test with the real embedding model (bge-small-en-v1.5) on the fixture files.

The model is downloaded to data/models on the first run (CI caches that folder).
"""

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk
from app.schemas.materials import MaterialKind
from app.services import materials as materials_service
from app.services.search.embedding import get_embedder
from app.services.search.search import search_module
from app.storage.local import LocalStorage
from tests.academics.conftest import Rows
from tests.search.conftest import run_jobs

FIXTURES = Path(__file__).parents[1] / "fixtures"

pytestmark = pytest.mark.real_embedder


async def test_an_exact_phrase_from_a_slide_ranks_that_slide_first(
    session: AsyncSession, alice: Rows, tmp_path: Path
) -> None:
    user_id, module_id = alice.user.id, alice.module.id
    storage = LocalStorage(tmp_path / "storage")
    uploaded = {}
    kinds: tuple[tuple[str, MaterialKind], ...] = (
        ("lecture.pdf", "slides"),
        ("slides.pptx", "slides"),
        ("notes.docx", "notes"),
    )
    for name, kind in kinds:
        with (FIXTURES / name).open("rb") as source:
            material = await materials_service.upload_material(
                session,
                storage,
                module_id,
                user_id=user_id,
                source=source,
                filename=name,
                kind=kind,
                title=None,
                allow_ai=True,
                max_bytes=10_000_000,
            )
        uploaded[name] = material.id

    assert await run_jobs(session, tmp_path) == 6  # extract + index for each file

    embedder = get_embedder()
    tokens = await session.scalars(select(Chunk.token_count).where(Chunk.user_id == user_id))
    assert all(0 < count <= 400 for count in tokens)

    found = await search_module(
        session,
        module_id,
        "Availability, modifiability, performance",
        user_id=user_id,
        embedder=embedder,
    )
    top = found.hits[0]
    assert (top.material_id, top.page_number) == (uploaded["slides.pptx"], 2)
    assert (top.vector_rank, top.keyword_rank) == (1, 1)

    # By meaning alone, with none of the slide's words.
    found = await search_module(
        session,
        module_id,
        "how data streams flow between processing steps",
        user_id=user_id,
        embedder=embedder,
    )
    assert (found.hits[0].material_id, found.hits[0].page_number) == (uploaded["lecture.pdf"], 3)
