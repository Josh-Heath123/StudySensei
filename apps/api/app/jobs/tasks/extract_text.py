"""Extract a material's text page by page into material_pages, then mark it ready.

Runs after every upload (and once for materials uploaded before extraction
existed). Re-running replaces the pages, so a retry never duplicates them.
"""

import asyncio
import uuid

from sqlalchemy import delete

from app.jobs.context import JobContext, JobError
from app.models import Material, MaterialPage
from app.services.extraction import ExtractionError, extract
from app.storage.base import blob_key


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
        raise JobError("The uploaded file is missing. Please upload it again.", retry=False)
    try:
        pages = await asyncio.to_thread(extract, material.content_type, path)
    except ExtractionError as exc:
        raise JobError(str(exc), retry=False) from exc  # the same file will fail the same way

    await ctx.session.execute(
        delete(MaterialPage).where(
            MaterialPage.user_id == material.user_id, MaterialPage.material_id == material.id
        )
    )
    ctx.session.add_all(
        MaterialPage(
            user_id=material.user_id,
            material_id=material.id,
            page_number=page.number,
            title=page.title,
            text=page.text,
            char_count=page.char_count,
            is_scanned=page.is_scanned,
        )
        for page in pages
    )
    material.page_count = len(pages)
    material.scanned_page_count = sum(page.is_scanned for page in pages)
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
