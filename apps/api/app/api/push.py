"""Web Push: the server's public key, this user's devices, and a test send (decision 0024).
Thin: ``app/services/push/`` does the work."""

import uuid

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser
from app.core import clock
from app.core.config import get_settings
from app.core.db import SessionDep
from app.schemas.push import (
    PushConfigOut,
    PushDeviceOutcomeOut,
    PushSubscriptionIn,
    PushSubscriptionOut,
    PushTestOut,
)
from app.services.errors import Conflict
from app.services.push import subscriptions
from app.services.push.payload import TEST_PAYLOAD
from app.services.push.sender import get_sender, push_enabled

router = APIRouter(tags=["push"])

TEST_TTL_SECONDS = 300


@router.get("/push/config", response_model=PushConfigOut)
async def get_push_config() -> PushConfigOut:
    """Whether reminders can be sent from this server, and the key to subscribe with."""
    enabled = push_enabled()
    return PushConfigOut(
        enabled=enabled, public_key=get_settings().vapid_public_key if enabled else None
    )


@router.post(
    "/push/subscriptions",
    response_model=PushSubscriptionOut,
    responses={201: {"model": PushSubscriptionOut}},
)
async def save_subscription(
    data: PushSubscriptionIn, session: SessionDep, user: CurrentUser, response: Response
) -> PushSubscriptionOut:
    """Save this browser's subscription (201), or refresh it if it's already saved (200)."""
    row, created = await subscriptions.upsert(
        session,
        user_id=user.id,
        endpoint=data.endpoint,
        p256dh=data.keys.p256dh,
        auth=data.keys.auth,
        label=data.label,
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return PushSubscriptionOut.model_validate(row)


@router.get("/push/subscriptions", response_model=list[PushSubscriptionOut])
async def list_subscriptions(session: SessionDep, user: CurrentUser) -> list[PushSubscriptionOut]:
    """Your devices with reminders on (never their endpoints)."""
    rows = await subscriptions.list_for(session, user_id=user.id)
    return [PushSubscriptionOut.model_validate(row) for row in rows]


@router.delete("/push/subscriptions/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subscription(
    subscription_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> None:
    await subscriptions.remove(session, subscription_id, user_id=user.id)


@router.post("/push/test", response_model=PushTestOut)
async def send_test(session: SessionDep, user: CurrentUser) -> PushTestOut:
    """Send "Reminders work" to each of your devices now, and say how each went."""
    sender = get_sender()
    if sender is None:
        raise Conflict("Reminders aren't set up on the server yet.")
    outcomes = await subscriptions.send_to_user(
        session,
        sender,
        user_id=user.id,
        payload=TEST_PAYLOAD,
        ttl=TEST_TTL_SECONDS,
        now=clock.now(),
    )
    return PushTestOut(
        devices=[PushDeviceOutcomeOut(id=o.id, label=o.label, outcome=o.outcome) for o in outcomes]
    )
