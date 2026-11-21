"""Web Push and the calendar feed (decision 0024)."""

import datetime as dt
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.schemas.academics import _Input

Endpoint = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=2000, pattern=r"^https://\S+$")
]
Key = Annotated[str, StringConstraints(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_=-]+$")]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class PushConfigOut(BaseModel):
    """Whether the server can send push (its VAPID keys are set), and the public key the
    browser subscribes with."""

    enabled: bool
    public_key: str | None


class PushKeysIn(_Input):
    p256dh: Key
    auth: Key


class PushSubscriptionIn(_Input):
    """A browser's PushSubscription, as ``subscription.toJSON()`` gives it, and a label."""

    endpoint: Endpoint
    keys: PushKeysIn
    label: Label


class PushSubscriptionOut(BaseModel):
    """A device: never its endpoint (a capability) or keys."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    created_at: dt.datetime
    last_success_at: dt.datetime | None


class PushDeviceOutcomeOut(BaseModel):
    id: uuid.UUID
    label: str
    # sent; failed (kept, counted); removed (gone, or failed 5 times in a row)
    outcome: Literal["sent", "failed", "removed"]


class PushTestOut(BaseModel):
    devices: list[PushDeviceOutcomeOut]


class CalendarFeedOut(BaseModel):
    """Whether a calendar link exists, and when it was made and last fetched. Never the token."""

    exists: bool
    created_at: dt.datetime | None
    last_fetched_at: dt.datetime | None


class CalendarFeedCreatedOut(BaseModel):
    """The private link, shown once."""

    url: str
    created_at: dt.datetime
