"""Write one practice generation's items with the AI (ADR 0025). Payload: ``generation_id``.

Queued by ``services.practice.generation.request_generation``. The flow is there; this
handler moves the generation through running → succeeded or failed:

- the sources and messages are prepared, then the transaction is committed, so none is held
  open while the AI answers;
- a reply that doesn't validate, even after a repair, is cut off, or is refused fails the
  generation at once with a readable error (asking again would fail the same way);
- ``AIUnavailable`` with a ``retry_at`` (rate limits, quotas) puts the generation back to
  queued and lets the worker reschedule the job; with none (no provider set up) it fails;
- at most ``MAX_CALLS`` provider calls per generation, across retries (``ai_usage.job_id``).
"""

import uuid

from app.ai.client import CallBudget, get_llm_client
from app.ai.errors import AIUnavailable
from app.ai.usage import job_calls
from app.core.config import get_settings
from app.jobs.context import JobContext, JobError
from app.services.errors import Invalid, NotFound
from app.services.practice.generation import (
    MAX_CALLS,
    GenerationFailed,
    ask,
    job_generation,
    mark,
    prepare,
    store,
)

UNEXPECTED = "Something went wrong while writing the practice items."


def _generation_id(ctx: JobContext) -> uuid.UUID:
    return uuid.UUID(str(ctx.job.payload["generation_id"]))


async def run(ctx: JobContext) -> None:
    user_id = ctx.job.user_id
    generation_id = _generation_id(ctx)
    try:
        generation, topic = await job_generation(ctx.session, generation_id, user_id=user_id)
    except NotFound:
        return  # its topic or module was deleted meanwhile
    if generation.status not in ("queued", "running"):
        return
    generation.status = "running"
    try:
        prepared = await prepare(
            ctx.session,
            topic,
            generation.requested,
            user_id=user_id,
            max_tokens=get_settings().practice_context_max_tokens,
        )
    except Invalid as exc:
        raise JobError(str(exc), retry=False) from exc
    spent = await job_calls(ctx.session, ctx.job.id, user_id=user_id)
    await ctx.session.commit()  # running, and no transaction held during the AI call

    budget = CallBudget(
        limit=MAX_CALLS,
        job_id=ctx.job.id,
        used=spent.ran,
        repairs_used=min(spent.invalid, 1),
        turned_away=spent.turned_away,
    )
    try:
        reply = await ask(get_llm_client(), prepared, user_id=user_id, budget=budget)
    except GenerationFailed as exc:
        raise JobError(str(exc), retry=False) from exc
    except AIUnavailable as exc:
        if exc.retry_at is not None:
            # Waiting for the providers, not running: the worker reschedules the job.
            await mark(ctx.session, generation_id, "queued", user_id=user_id)
        raise
    await store(ctx.session, generation_id, prepared, reply, user_id=user_id, now=ctx.now())


async def on_failure(ctx: JobContext, message: str, *, retrying: bool) -> None:
    """Record the failure on the generation: queued again while the job retries, else
    failed with the message (a JobError's own words; a generic sentence otherwise)."""
    from app.jobs.worker import GAVE_UP
    from app.jobs.worker import UNEXPECTED as WORKER_UNEXPECTED

    user_id = ctx.job.user_id
    if retrying:
        await mark(ctx.session, _generation_id(ctx), "queued", user_id=user_id)
        return
    readable = UNEXPECTED if message in (GAVE_UP, WORKER_UNEXPECTED) else message
    await mark(
        ctx.session, _generation_id(ctx), "failed", user_id=user_id, error=readable, now=ctx.now()
    )
