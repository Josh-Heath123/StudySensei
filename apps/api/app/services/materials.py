"""Course materials: upload (with dedupe), list, edit, delete and retry.

Uploads are spooled to a temporary file while they're hashed and counted, checked
by content (``filetypes.detect``), stored under ``{user_id}/{sha256}`` and
queued for processing in the same transaction as the new row.
"""

import asyncio
import hashlib
import tempfile
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import BinaryIO

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs import queue
from app.jobs.kinds import EXTRACT_TEXT
from app.models import Job, Material, MaterialPage
from app.schemas.materials import MaterialKind, MaterialUpdate
from app.services.academics.modules import get_module
from app.services.errors import Conflict, Invalid, NotFound, TooLarge, Unsupported
from app.services.filetypes import NotAllowed, detect
from app.storage.base import Storage, blob_key

_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class Spooled:
    path: Path
    sha256: str
    size: int


def _spool(source: BinaryIO, limit: int) -> Spooled:
    """Copy ``source`` to a temporary file, hashing and counting. Raises TooLarge."""
    digest = hashlib.sha256()
    size = 0
    with tempfile.NamedTemporaryFile(prefix="upload-", delete=False) as out:
        path = Path(out.name)
        try:
            while chunk := source.read(_CHUNK):
                size += len(chunk)
                if size > limit:
                    raise TooLarge(f"Files can be at most {limit // (1024 * 1024)} MB.")
                digest.update(chunk)
                out.write(chunk)
        except BaseException:
            out.close()
            path.unlink(missing_ok=True)
            raise
    return Spooled(path, digest.hexdigest(), size)


@asynccontextmanager
async def _spooled(source: BinaryIO, limit: int) -> AsyncIterator[Spooled]:
    spooled = await asyncio.to_thread(_spool, source, limit)
    try:
        yield spooled
    finally:
        spooled.path.unlink(missing_ok=True)  # gone already if Storage took it


def _title_from(filename: str) -> str:
    stem = PurePath(filename).stem.replace("_", " ").strip()
    return (stem or "Untitled")[:200]


async def upload_material(
    session: AsyncSession,
    storage: Storage,
    module_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
    source: BinaryIO,
    filename: str,
    kind: MaterialKind,
    title: str | None,
    allow_ai: bool,
    max_bytes: int,
) -> Material:
    await get_module(session, module_id, user_id=user_id)
    filename = PurePath(filename.replace("\\", "/")).name[:255]  # never trust a client path
    async with _spooled(source, max_bytes) as spooled:
        if spooled.size == 0:
            raise Invalid("The file is empty.")
        try:
            allowed = await asyncio.to_thread(detect, filename, spooled.path)
        except NotAllowed as exc:
            raise Unsupported(str(exc)) from exc

        existing = await _in_module(session, module_id, spooled.sha256, user_id=user_id)
        if existing is not None:
            raise Conflict(f"This file is already in the module as “{existing.title}”.")

        material = Material(
            user_id=user_id,
            module_id=module_id,
            kind=kind,
            title=(title or "").strip()[:200] or _title_from(filename),
            original_filename=filename,
            content_type=allowed.content_type,
            size_bytes=spooled.size,
            sha256=spooled.sha256,
            allow_ai=allow_ai,
        )
        try:
            async with session.begin_nested():
                session.add(material)
                await session.flush()
        except IntegrityError as exc:
            if "uq_materials_module_sha256" not in str(exc.orig):
                raise
            raise Conflict("This file is already in the module.") from exc

        # Always (re)write the blob: atomic, and a concurrent delete can't leave a row without one.
        await asyncio.to_thread(storage.put, blob_key(user_id, spooled.sha256), spooled.path)
        queue.enqueue(session, EXTRACT_TEXT, {"material_id": str(material.id)}, user_id=user_id)
        await session.commit()
        await session.refresh(material)
        return material


async def _in_module(
    session: AsyncSession, module_id: uuid.UUID, sha256: str, *, user_id: uuid.UUID
) -> Material | None:
    return await session.scalar(
        select(Material).where(
            Material.user_id == user_id, Material.module_id == module_id, Material.sha256 == sha256
        )
    )


async def list_materials(
    session: AsyncSession, module_id: uuid.UUID, *, user_id: uuid.UUID
) -> list[Material]:
    """The module's materials, newest first."""
    await get_module(session, module_id, user_id=user_id)
    result = await session.scalars(
        select(Material)
        .where(Material.user_id == user_id, Material.module_id == module_id)
        .order_by(Material.created_at.desc(), Material.id.desc())
    )
    return list(result)


async def get_material(
    session: AsyncSession, material_id: uuid.UUID, *, user_id: uuid.UUID
) -> Material:
    material = await session.scalar(
        select(Material).where(Material.id == material_id, Material.user_id == user_id)
    )
    if material is None:
        raise NotFound("Material")
    return material


async def update_material(
    session: AsyncSession, material_id: uuid.UUID, data: MaterialUpdate, *, user_id: uuid.UUID
) -> Material:
    material = await get_material(session, material_id, user_id=user_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(material, field, value)
    await session.commit()
    await session.refresh(material)
    return material


async def _forget_blobs(
    session: AsyncSession, storage: Storage, hashes: set[str], *, user_id: uuid.UUID
) -> None:
    """Delete the blobs no material of this user uses any more (after the delete is committed)."""
    if not hashes:
        return
    used = set(
        await session.scalars(
            select(Material.sha256).where(Material.user_id == user_id, Material.sha256.in_(hashes))
        )
    )
    for sha256 in hashes - used:
        await asyncio.to_thread(storage.delete, blob_key(user_id, sha256))


async def delete_material(
    session: AsyncSession, storage: Storage, material_id: uuid.UUID, *, user_id: uuid.UUID
) -> None:
    material = await get_material(session, material_id, user_id=user_id)
    sha256 = material.sha256
    await _delete_jobs_for(session, [material.id], user_id=user_id)
    await session.delete(material)
    await session.commit()
    await _forget_blobs(session, storage, {sha256}, user_id=user_id)


async def delete_module_materials(
    session: AsyncSession, storage: Storage, module_id: uuid.UUID, *, user_id: uuid.UUID
) -> None:
    """Remove a module's materials and their now-unused blobs (before the module is deleted)."""
    await get_module(session, module_id, user_id=user_id)
    rows = (
        await session.execute(
            select(Material.id, Material.sha256).where(
                Material.user_id == user_id, Material.module_id == module_id
            )
        )
    ).all()
    if not rows:
        return
    await _delete_jobs_for(session, [row.id for row in rows], user_id=user_id)
    await session.execute(
        delete(Material).where(Material.user_id == user_id, Material.module_id == module_id)
    )
    await session.commit()
    await _forget_blobs(session, storage, {row.sha256 for row in rows}, user_id=user_id)


async def _delete_jobs_for(
    session: AsyncSession, material_ids: list[uuid.UUID], *, user_id: uuid.UUID
) -> None:
    """Drop unfinished jobs for these materials (nothing left to process)."""
    ids = [str(material_id) for material_id in material_ids]
    await session.execute(
        delete(Job).where(
            Job.user_id == user_id,
            Job.status.in_(("queued", "running")),
            Job.payload["material_id"].astext.in_(ids),
        )
    )


async def retry_material(
    session: AsyncSession, material_id: uuid.UUID, *, user_id: uuid.UUID
) -> Material:
    """Queue a failed material for processing again."""
    material = await get_material(session, material_id, user_id=user_id)
    if material.status != "failed":
        raise Invalid("Only a material that failed can be retried.")
    material.status = "uploaded"
    material.error = None
    queue.enqueue(session, EXTRACT_TEXT, {"material_id": str(material.id)}, user_id=user_id)
    await session.commit()
    await session.refresh(material)
    return material


async def list_pages(
    session: AsyncSession, material_id: uuid.UUID, *, user_id: uuid.UUID
) -> list[MaterialPage]:
    """The material's extracted pages in order (empty until extraction has run)."""
    await get_material(session, material_id, user_id=user_id)
    result = await session.scalars(
        select(MaterialPage)
        .where(MaterialPage.user_id == user_id, MaterialPage.material_id == material_id)
        .order_by(MaterialPage.page_number)
    )
    return list(result)


async def get_page(
    session: AsyncSession, material_id: uuid.UUID, page_number: int, *, user_id: uuid.UUID
) -> MaterialPage:
    await get_material(session, material_id, user_id=user_id)
    page = await session.scalar(
        select(MaterialPage).where(
            MaterialPage.user_id == user_id,
            MaterialPage.material_id == material_id,
            MaterialPage.page_number == page_number,
        )
    )
    if page is None:
        raise NotFound("Page")
    return page


@dataclass
class MaterialFile:
    """An open handle on a material's stored original, and what to serve it as."""

    material: Material
    size: int
    stream: BinaryIO


async def open_file(
    session: AsyncSession, storage: Storage, material_id: uuid.UUID, *, user_id: uuid.UUID
) -> MaterialFile:
    """The stored original. Another user's material, or a blob that's gone, is NotFound."""
    material = await get_material(session, material_id, user_id=user_id)
    try:
        stream = storage.open(blob_key(user_id, material.sha256))
    except FileNotFoundError:
        raise NotFound("File") from None
    size = stream.seek(0, 2)
    stream.seek(0)
    return MaterialFile(material, size, stream)
