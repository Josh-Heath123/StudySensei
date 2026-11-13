"""Migration 0006 queues text extraction for materials uploaded before it existed."""

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

PATH = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0006_material_pages.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0006", PATH)
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
        error="Old error" if status == "failed" else None,
    )


async def test_every_material_gets_one_extract_text_job(session: AsyncSession, alice: Rows) -> None:
    user_id = alice.user.id
    ready = a_material(alice, "a", "ready")  # counted pages, finished job
    waiting = a_material(alice, "b", "uploaded")  # its count_pages job is still queued
    failed = a_material(alice, "c", "failed")
    session.add_all([ready, waiting, failed])
    await session.flush()
    done = queue.enqueue(session, "count_pages", {"material_id": str(ready.id)}, user_id=user_id)
    done.status, done.finished_at = "succeeded", done.created_at
    queue.enqueue(session, "count_pages", {"material_id": str(waiting.id)}, user_id=user_id)
    await session.flush()

    def run(sync_connection: object) -> None:
        context = MigrationContext.configure(sync_connection)  # type: ignore[arg-type]
        with Operations.context(context):
            migration.queue_extraction()

    await (await session.connection()).run_sync(run)

    result = await session.execute(
        select(Job.kind, Job.status, Job.payload["material_id"].astext).where(
            Job.user_id == user_id
        )
    )
    jobs = sorted((kind, status, material) for kind, status, material in result)
    assert jobs == sorted(
        [
            ("count_pages", "succeeded", str(ready.id)),  # history is left alone
            ("extract_text", "queued", str(waiting.id)),  # renamed, not duplicated
            ("extract_text", "queued", str(ready.id)),
            ("extract_text", "queued", str(failed.id)),
        ]
    )
    statuses = await session.execute(
        select(Material.status, Material.error)
        .where(Material.user_id == user_id)
        .execution_options(populate_existing=True)
    )
    assert set(statuses) == {("uploaded", None)}
