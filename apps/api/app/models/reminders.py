"""Reminders (Phase 4, decision 0024): Web Push subscriptions, the reminders already sent,
and the private calendar feed.

A **push subscription** is one browser's endpoint and keys (RFC 8030/8291), with a label
from its user agent ("Edge on Windows"). The endpoint is a capability: anyone who has it can
push to that browser, so it's never logged or returned. ``failures`` counts failed sends in
a row; a 404/410 or the fifth failure deletes the row.

A **sent reminder** is keyed by its slot (``slot_key``: a sha256 of the block's start, end,
assessment and topic), not the block's id: every plan version gives blocks new ids, so the
slot is what keeps one reminder per block across re-plans.

A **calendar feed** stores only the sha256 of its token. The token is shown once, when the
link is created or reset.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedBase


class PushSubscription(TimestampedBase):
    __tablename__ = "push_subscriptions"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_push_subscriptions_id_user"),
        UniqueConstraint("user_id", "endpoint", name="uq_push_subscriptions_user_endpoint"),
        CheckConstraint("endpoint LIKE 'https://%'", name="ck_push_subscriptions_https"),
        CheckConstraint("failures >= 0", name="ck_push_subscriptions_failures"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    endpoint: Mapped[str] = mapped_column(Text)
    # The browser's public key (P-256, base64url) and auth secret, for RFC 8291 encryption.
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    label: Mapped[str] = mapped_column(String(100))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failures: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class ReminderSent(TimestampedBase):
    __tablename__ = "reminders_sent"
    __table_args__ = (UniqueConstraint("user_id", "slot_key", name="uq_reminders_sent_user_slot"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    slot_key: Mapped[str] = mapped_column(String(64))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CalendarFeed(TimestampedBase):
    __tablename__ = "calendar_feeds"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_calendar_feeds_user"),
        UniqueConstraint("token_hash", name="uq_calendar_feeds_token_hash"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # sha256 of the token, hex. The token itself is never stored.
    token_hash: Mapped[str] = mapped_column(String(64))
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
