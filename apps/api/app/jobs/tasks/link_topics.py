"""Rebuild a module's chunk ↔ topic links (no AI calls; decision 0006).

Queued when topics are added or edited, and when a material that isn't analysed for
topics is indexed. The merge job relinks by itself.
"""

from app.jobs.context import JobContext
from app.jobs.queue import enqueue_replan
from app.jobs.tasks.merge_topics import job_module, relink


async def run(ctx: JobContext) -> None:
    module = await job_module(ctx)
    if module is None:
        return
    module_id = module.id
    await ctx.session.commit()
    await relink(ctx, module_id)
    # New links change topic workloads: re-plan (decision 0021).
    await enqueue_replan(
        ctx.session,
        user_id=ctx.job.user_id,
        trigger="material",
        detail={"module_id": str(module_id)},
    )
    await ctx.session.commit()
