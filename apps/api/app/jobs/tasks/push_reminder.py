"""Send one block's reminder to every push subscription the job's user has (decision 0024).
Queued by ``services.push.reminders.queue_reminders``, one attempt only: a retry would send
it again to the devices that already got it. Each device's outcome is recorded on its row.

The TTL is worked out here, when sending, from the block's start: a reminder that waited in
the queue (or was run again) lives only until the block starts, and once it has started the
job is dropped without sending, so a reminder never arrives late.
"""

import logging
from datetime import datetime

from app.jobs.context import JobContext
from app.services.push.sender import get_sender
from app.services.push.subscriptions import send_to_user

log = logging.getLogger("studysensei.push")


async def run(ctx: JobContext) -> None:
    sender = get_sender()
    if sender is None:
        return  # push was turned off on the server since this was queued
    payload = ctx.job.payload
    now = ctx.now()
    if "start_at" in payload:
        left = int((datetime.fromisoformat(payload["start_at"]) - now).total_seconds())
        if left <= 0:
            log.info("Reminder job %s dropped: its block has started", ctx.job.id)
            return
        ttl = left
    else:
        ttl = int(payload["ttl"])  # queued before the TTL moved here
    await send_to_user(
        ctx.session,
        sender,
        user_id=ctx.job.user_id,
        payload=payload["payload"],
        ttl=ttl,
        now=now,
    )
