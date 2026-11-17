"""Migration 0011 queues topic extraction once for each eligible, indexed material."""

import importlib.util
from pathlib import Path
from types import ModuleType

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Job, Material, User
from tests.academics.conftest import make_rows

PATH = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0011_topic_maps.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0011", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = load()


async def test_each_eligible_indexed_material_gets_one_extraction(
    session: AsyncSession, user_a: User
) -> None:
    rows = await make_rows(session, user_a)
    user_id, module_id = rows.user.id, rows.module.id

    def material(
        title: str, kind: str = "slides", status: str = "ready", ai: bool = True
    ) -> Material:
        return Material(
            user_id=user_id,
            module_id=module_id,
            kind=kind,
            title=title,
            original_filename=f"{title}.pdf",
            content_type="application/pdf",
            size_bytes=10,
            sha256=title[0] * 64,
            status=status,
            allow_ai=ai,
        )

    slides, notes = material("a"), material("b", kind="notes")
    others = [
        material("c", kind="past_paper"),
        material("d", ai=False),
        material("e", status="processing"),  # index_material will queue its own
        material("f", status="failed"),
    ]
    session.add_all([slides, notes, *others])
    await session.flush()
    session.add(
        Job(
            user_id=user_id,
            kind="extract_topics",
            payload={"material_id": str(notes.id), "module_id": str(module_id)},
        )
    )
    await session.flush()

    def run(sync_connection: object) -> None:
        context = MigrationContext.configure(sync_connection)  # type: ignore[arg-type]
        with Operations.context(context):
            migration.queue_extraction()

    await (await session.connection()).run_sync(run)

    jobs = await session.execute(
        select(Job.payload["material_id"].astext, Job.payload["module_id"].astext).where(
            Job.user_id == user_id, Job.kind == "extract_topics"
        )
    )
    assert sorted(tuple(row) for row in jobs) == sorted(
        [(str(slides.id), str(module_id)), (str(notes.id), str(module_id))]  # not duplicated
    )
