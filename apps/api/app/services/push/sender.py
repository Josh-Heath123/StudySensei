"""Sending one Web Push message (decision 0024).

``PushSender`` is the seam: ``WebPushSender`` encrypts the payload end to end (RFC 8291,
aes128gcm) and signs a VAPID header with pywebpush; ``FakePushSender`` records what it would
send, for tests, which never reach the network. Push is *disabled*, not an error, when the
VAPID keys aren't set: ``get_sender()`` is then None.

The endpoint is a capability (anyone holding it can push to that browser), so nothing here
logs it.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

import aiohttp
from py_vapid import Vapid02
from pywebpush import WebPushException, webpush_async

from app.core.config import get_settings

TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class Target:
    """Where to send: one subscription's endpoint and keys."""

    endpoint: str
    p256dh: str
    auth: str


@dataclass(frozen=True)
class Sent:
    """The push service's answer: its HTTP status, or None if it couldn't be reached."""

    status: int | None

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 300


class PushSender(Protocol):
    async def send(self, target: Target, payload: Mapping[str, Any], *, ttl: int) -> Sent: ...


class WebPushSender:
    """pywebpush with a VAPID key: the real thing."""

    def __init__(self, private_key: str, subject: str) -> None:
        self._vapid = Vapid02.from_string(private_key)
        self._subject = subject

    async def send(self, target: Target, payload: Mapping[str, Any], *, ttl: int) -> Sent:
        try:
            response = await webpush_async(
                {
                    "endpoint": target.endpoint,
                    "keys": {"p256dh": target.p256dh, "auth": target.auth},
                },
                data=json.dumps(payload, ensure_ascii=False),
                vapid_private_key=self._vapid,
                vapid_claims={"sub": self._subject},
                ttl=ttl,
                timeout=TIMEOUT_SECONDS,
            )
        except WebPushException as exc:
            status = getattr(exc.response, "status", None) or getattr(
                exc.response, "status_code", None
            )
            return Sent(int(status) if status is not None else None)
        except (aiohttp.ClientError, TimeoutError, OSError):
            return Sent(None)
        return Sent(getattr(response, "status", 201))


@dataclass
class FakePushSender:
    """Records each send; answers with ``statuses`` by endpoint (default 201)."""

    statuses: dict[str, int | None] = field(default_factory=dict)
    sent: list[tuple[Target, dict[str, Any], int]] = field(default_factory=list)

    async def send(self, target: Target, payload: Mapping[str, Any], *, ttl: int) -> Sent:
        self.sent.append((target, dict(payload), ttl))
        return Sent(self.statuses.get(target.endpoint, 201))


_override: PushSender | None = None


def set_sender(sender: PushSender | None) -> None:
    """Use ``sender`` instead of the configured one (tests)."""
    global _override
    _override = sender


def push_enabled() -> bool:
    """Whether the VAPID keys and subject are set."""
    settings = get_settings()
    return bool(settings.vapid_public_key and settings.vapid_private_key and settings.vapid_subject)


def get_sender() -> PushSender | None:
    """The sender to use, or None when push is disabled."""
    if not push_enabled():
        return None
    if _override is not None:
        return _override
    settings = get_settings()
    assert settings.vapid_private_key is not None and settings.vapid_subject is not None
    return WebPushSender(settings.vapid_private_key.get_secret_value(), settings.vapid_subject)
