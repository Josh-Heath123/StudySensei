import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs import queue
from app.jobs.kinds import INDEX_MATERIAL
from app.jobs.worker import run_once
from app.models import Material, MaterialPage, Module, User
from app.storage.local import LocalStorage
from tests.academics.conftest import Rows, make_rows


@pytest.fixture
async def alice(session: AsyncSession, user_a: User) -> Rows:
    return await make_rows(session, user_a)


@pytest.fixture
async def bob(session: AsyncSession, user_b: User) -> Rows:
    return await make_rows(session, user_b)


@dataclass(frozen=True)
class Page:
    text: str
    title: str | None = None
    scanned: bool = False


async def add_material(
    session: AsyncSession,
    user: User,
    module: Module,
    title: str,
    pages: list[Page],
    *,
    queue_index: bool = True,
) -> Material:
    """An extracted material (its pages stored) with its index_material job queued."""
    material = Material(
        user_id=user.id,
        module_id=module.id,
        kind="slides",
        title=title,
        original_filename=f"{title}.pdf",
        content_type="application/pdf",
        size_bytes=10,
        sha256=hashlib.sha256(title.encode()).hexdigest(),
        status="processing",
        page_count=len(pages),
    )
    session.add(material)
    await session.flush()
    session.add_all(
        MaterialPage(
            user_id=user.id,
            material_id=material.id,
            page_number=number,
            title=page.title,
            text=page.text,
            char_count=len(page.text),
            is_scanned=page.scanned,
        )
        for number, page in enumerate(pages, start=1)
    )
    if queue_index:
        queue.enqueue(session, INDEX_MATERIAL, {"material_id": str(material.id)}, user_id=user.id)
    await session.commit()
    return material


async def run_jobs(session: AsyncSession, tmp_path: Path) -> int:
    """Run the worker on the test session until the queue is empty. Returns jobs run."""

    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        yield session

    storage = LocalStorage(tmp_path / "storage")
    later = datetime.now(UTC) + timedelta(hours=1)
    ran = 0
    while await run_once(sessions, storage, now=lambda: later):
        ran += 1
    return ran
