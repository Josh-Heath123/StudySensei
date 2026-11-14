"""Migration 0007 queues indexing for materials already extracted."""

import importlib.util
from pathlib import Path
from types import ModuleType

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs import queue
from app.models import Job, Material
from tests.academics.conftest import Rows

PATH = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0007_chunks.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0007", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = load()


def a_material(rows: Rows, sha: str, status: str) -> Material:
    return Material(
        user_id=rows.user.id,
        module_id=rows.module.id,
        kind="slides",
        title=sha,
        original_filename=f"{sha}.pdf",
        content_type="application/pdf",
        size_bytes=10,
        sha256=sha * 64,
        status=status,
        page_count=3 if status == "ready" else None,
        error="Couldn't read it." if status == "failed" else None,
    )


async def test_extracted_materials_go_back_to_processing_with_one_index_job(
    session: AsyncSession, alice: Rows
) -> None:
    user_id = alice.user.id
    ready = a_material(alice, "a", "ready")
    queued = a_material(alice, "b", "ready")  # already has an index job waiting
    extracting = a_material(alice, "c", "processing")  # extract_text will queue its own
    failed = a_material(alice, "d", "failed")
    session.add_all([ready, queued, extracting, failed])
    await session.flush()
    queue.enqueue(session, "index_material", {"material_id": str(queued.id)}, user_id=user_id)
    await session.flush()

    def run(sync_connection: object) -> None:
        context = MigrationContext.configure(sync_connection)  # type: ignore[arg-type]
        with Operations.context(context):
            migration.queue_indexing()

    await (await session.connection()).run_sync(run)

    result = await session.execute(
        select(Job.kind, Job.status, Job.payload["material_id"].astext).where(
            Job.user_id == user_id
        )
    )
    assert sorted(tuple(row) for row in result) == sorted(
        [
            ("index_material", "queued", str(ready.id)),
            ("index_material", "queued", str(queued.id)),  # not duplicated
        ]
    )
    statuses = await session.execute(
        select(Material.title, Material.status)
        .where(Material.user_id == user_id)
        .execution_options(populate_existing=True)
    )
    assert {title: status for title, status in statuses} == {
        "a": "processing",
        "b": "processing",
        "c": "processing",
        "d": "failed",
    }
