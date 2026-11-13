"""The first processing step: count a material's pages and mark it ready.

Text extraction replaces this in the next task; the job system stays the same.
"""

import asyncio
import re
import uuid
import zipfile
from pathlib import Path

import pypdfium2 as pdfium

from app.jobs.context import JobContext, JobError
from app.models import Material
from app.services.filetypes import ALLOWED
from app.storage.base import blob_key

_SLIDE = re.compile(r"^ppt/slides/slide\d+\.xml$")
_PAGES = re.compile(rb"<(?:\w+:)?Pages>\s*(\d+)\s*</(?:\w+:)?Pages>")
# docProps/app.xml is tiny; never read more than this from it.
_APP_XML_LIMIT = 64 * 1024

_TYPE_BY_CONTENT_TYPE = {allowed.content_type: allowed.type for allowed in ALLOWED.values()}


def page_count(content_type: str, path: Path) -> int | None:
    """Pages (PDF, DOCX), slides (PPTX) or 1 (an image). None for text, or when unknown."""
    match _TYPE_BY_CONTENT_TYPE.get(content_type):
        case "pdf":
            return _pdf_pages(path)
        case "pptx":
            with zipfile.ZipFile(path) as archive:
                return sum(1 for name in archive.namelist() if _SLIDE.match(name))
        case "docx":
            return _docx_pages(path)
        case "png" | "jpg":
            return 1
        case _:
            return None


def _pdf_pages(path: Path) -> int:
    try:
        document = pdfium.PdfDocument(path)
    except pdfium.PdfiumError as exc:
        raise JobError(
            "The PDF couldn't be opened. It may be damaged or password-protected."
        ) from exc
    try:
        return len(document)
    finally:
        document.close()


def _docx_pages(path: Path) -> int | None:
    """Word records the page count when it saves; other tools may not."""
    with zipfile.ZipFile(path) as archive:
        if "docProps/app.xml" not in archive.namelist():
            return None
        with archive.open("docProps/app.xml") as f:
            match = _PAGES.search(f.read(_APP_XML_LIMIT))
    return int(match.group(1)) if match else None


async def _material(ctx: JobContext) -> Material | None:
    material_id = uuid.UUID(str(ctx.job.payload["material_id"]))
    material: Material | None = await ctx.session.get(Material, material_id)
    # Scoped by the job's user, like every query.
    return material if material is not None and material.user_id == ctx.job.user_id else None


async def run(ctx: JobContext) -> None:
    material = await _material(ctx)
    if material is None:
        return  # deleted since it was queued: nothing to do
    material.status = "processing"
    await ctx.session.commit()

    path = ctx.storage.path_for(blob_key(material.user_id, material.sha256))
    if not path.is_file():
        raise JobError("The uploaded file is missing. Please upload it again.")
    material.page_count = await asyncio.to_thread(page_count, material.content_type, path)
    material.status = "ready"
    material.error = None
    await ctx.session.commit()


async def on_failure(ctx: JobContext, message: str, *, retrying: bool) -> None:
    material = await _material(ctx)
    if material is None:
        return
    material.status = "processing" if retrying else "failed"
    material.error = message
    await ctx.session.commit()
