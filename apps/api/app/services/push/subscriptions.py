"""Push subscriptions and sending to them (decision 0024). Scoped by ``user_id``.

Outcomes of a send: success sets ``last_success_at`` and ``failures = 0``; a 404 or 410 (the
browser unsubscribed, or the subscription expired) deletes the row; any other failure adds 1,
and the fifth in a row deletes it. Logs name the subscription's id, never its endpoint.
"""

import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import Boolean, delete, func, literal_column, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PushSubscription
from app.services.errors import NotFound
from app.services.push.sender import PushSender, Target

log = logging.getLogger("studysensei.push")

MAX_FAILURES = 5
GONE = (404, 410)

Outcome = Literal["sent", "failed", "removed"]


@dataclass(frozen=True)
class DeviceOutcome:
    id: uuid.UUID
    label: str
    outcome: Outcome


async def upsert(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    endpoint: str,
    p256dh: str,
    auth: str,
    label: str,
) -> tuple[PushSubscription, bool]:
    """Save this browser's subscription for the user, or refresh its keys and label if the
    endpoint is already saved. Returns the row and whether it was created."""
    result = await session.execute(
        insert(PushSubscription)
        .values(
            id=uuid.uuid4(),
            user_id=user_id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            label=label,
        )
        .on_conflict_do_update(
            constraint="uq_push_subscriptions_user_endpoint",
            set_={
                "p256dh": p256dh,
                "auth": auth,
                "label": label,
                "failures": 0,
                "updated_at": func.now(),
            },
        )
        # xmax is 0 on a row this statement inserted (Postgres), not on one it updated.
        .returning(PushSubscription.id, literal_column("xmax = 0", Boolean))
    )
    row = result.one()
    row_id, created = row[0], bool(row[1])
    await session.commit()
    found = await session.get(PushSubscription, row_id, populate_existing=True)
    assert found is not None
    return found, created


async def list_for(session: AsyncSession, *, user_id: uuid.UUID) -> list[PushSubscription]:
    return list(
        await session.scalars(
            select(PushSubscription)
            .where(PushSubscription.user_id == user_id)
            .order_by(PushSubscription.created_at)
        )
    )


async def remove(session: AsyncSession, subscription_id: uuid.UUID, *, user_id: uuid.UUID) -> None:
    deleted = await session.execute(
        delete(PushSubscription)
        .where(PushSubscription.id == subscription_id, PushSubscription.user_id == user_id)
        .returning(PushSubscription.id)
    )
    if deleted.first() is None:
        raise NotFound("Push subscription")
    await session.commit()


async def send_to_user(
    session: AsyncSession,
    sender: PushSender,
    *,
    user_id: uuid.UUID,
    payload: Mapping[str, Any],
    ttl: int,
    now: datetime,
) -> list[DeviceOutcome]:
    """Send ``payload`` to each of the user's subscriptions and record each outcome."""
    outcomes = []
    for sub in await list_for(session, user_id=user_id):
        sent = await sender.send(Target(sub.endpoint, sub.p256dh, sub.auth), payload, ttl=ttl)
        outcome: Outcome
        if sent.ok:
            sub.last_success_at = now
            sub.failures = 0
            outcome = "sent"
        elif sent.status in GONE:
            log.info("Push subscription %s is gone (%s); removed", sub.id, sent.status)
            await session.delete(sub)
            outcome = "removed"
        else:
            sub.failures += 1
            if sub.failures >= MAX_FAILURES:
                log.warning(
                    "Push subscription %s failed %s times in a row (last %s); removed",
                    sub.id,
                    sub.failures,
                    sent.status,
                )
                await session.delete(sub)
                outcome = "removed"
            else:
                log.info("Push to subscription %s failed (%s)", sub.id, sent.status)
                outcome = "failed"
        outcomes.append(DeviceOutcome(sub.id, sub.label, outcome))
    await session.commit()
    return outcomes
