"""Send one block's reminder to every push subscription the job's user has (decision 0024).
Queued by ``services.push.reminders.queue_reminders``, one attempt only: a retry would send
it again to the devices that already got it. Each device's outcome is recorded on its row."""

from app.core import clock
from app.jobs.context import JobContext
from app.services.push.sender import get_sender
from app.services.push.subscriptions import send_to_user


async def run(ctx: JobContext) -> None:
    sender = get_sender()
    if sender is None:
        return  # push was turned off on the server since this was queued
    payload = ctx.job.payload
    await send_to_user(
        ctx.session,
        sender,
        user_id=ctx.job.user_id,
        payload=payload["payload"],
        ttl=int(payload["ttl"]),
        now=clock.now(),
    )
