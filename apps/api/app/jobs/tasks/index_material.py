"""Chunk and embed a material's extracted pages into chunks, then mark it ready.

Queued by extract_text when it succeeds. Re-running replaces the material's chunks,
so a retry never duplicates them. Scanned pages are skipped until a vision step
reads them. Embedding is local, so it runs whatever ``allow_ai`` says (decision 0005).
"""

import asyncio

from sqlalchemy import delete, insert, select

from app.jobs.context import JobContext
from app.jobs.tasks.extract_text import job_material, record_failure
from app.models import Chunk, MaterialPage
from app.services.search.embedding import get_embedder
from app.services.search.indexing import PageText, build_chunks

_INSERT_BATCH = 200


async def run(ctx: JobContext) -> None:
    material = await job_material(ctx)
    if material is None:
        return  # deleted since it was queued
    user_id = material.user_id
    rows = await ctx.session.execute(
        select(MaterialPage.page_number, MaterialPage.title, MaterialPage.text)
        .where(
            MaterialPage.user_id == user_id,
            MaterialPage.material_id == material.id,
            MaterialPage.is_scanned.is_(False),
        )
        .order_by(MaterialPage.page_number)
    )
    pages = [PageText(number, title, text) for number, title, text in rows]
    title = material.title
    await ctx.session.commit()  # don't hold a transaction open while embedding

    embedder = await asyncio.to_thread(get_embedder)
    chunks = await asyncio.to_thread(build_chunks, embedder, title, pages)

    material = await job_material(ctx)
    if material is None:
        return
    await ctx.session.execute(
        delete(Chunk).where(Chunk.user_id == user_id, Chunk.material_id == material.id)
    )
    values = [
        {
            "user_id": user_id,
            "module_id": material.module_id,
            "material_id": material.id,
            "page_number": chunk.page_number,
            "position": chunk.position,
            "text": chunk.text,
            "token_count": chunk.token_count,
            "embedding": chunk.embedding,
        }
        for chunk in chunks
    ]
    for start in range(0, len(values), _INSERT_BATCH):
        await ctx.session.execute(insert(Chunk), values[start : start + _INSERT_BATCH])
    material.status = "ready"
    material.error = None
    await ctx.session.commit()


on_failure = record_failure
