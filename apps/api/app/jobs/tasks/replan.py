"""Re-plan for the job's user (decision 0021). Queued by ``queue.enqueue_replan`` when a
change commits, and nightly. No ``on_failure``: the worker's failure messages are about
files, and a failed re-plan only leaves the current version in place until the next one."""

from datetime import UTC, datetime

from app.jobs.context import JobContext
from app.services.planning.replan import replan


async def run(ctx: JobContext) -> None:
    payload = ctx.job.payload
    await replan(
        ctx.session,
        user_id=ctx.job.user_id,
        now=datetime.now(UTC),
        trigger=str(payload.get("trigger", "manual")),
        detail=payload.get("detail") or {},
    )
