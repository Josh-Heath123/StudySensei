"""Reminders: Web Push subscriptions, sent reminders, the calendar feed, and
users.reminder_minutes (Phase 4, decision 0024).

- push_subscriptions: one browser's endpoint (https only) and keys; UNIQUE (user_id,
  endpoint) and UNIQUE (id, user_id).
- reminders_sent: one row per reminded slot; UNIQUE (user_id, slot_key).
- calendar_feeds: one per user (UNIQUE user_id), the token's sha256 (UNIQUE token_hash).
- users.reminder_minutes: null (off), 5, 10, 15 or 30; default 10.

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _user() -> sa.Column[object]:
    return sa.Column(
        "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        *_timestamps(),
        _user(),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.String(200), nullable=False),
        sa.Column("auth", sa.String(100), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failures", sa.Integer(), server_default="0", nullable=False),
        sa.UniqueConstraint("id", "user_id", name="uq_push_subscriptions_id_user"),
        sa.UniqueConstraint("user_id", "endpoint", name="uq_push_subscriptions_user_endpoint"),
        sa.CheckConstraint("endpoint LIKE 'https://%'", name="ck_push_subscriptions_https"),
        sa.CheckConstraint("failures >= 0", name="ck_push_subscriptions_failures"),
    )
    op.create_table(
        "reminders_sent",
        *_timestamps(),
        _user(),
        sa.Column("slot_key", sa.String(64), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "slot_key", name="uq_reminders_sent_user_slot"),
    )
    op.create_table(
        "calendar_feeds",
        *_timestamps(),
        _user(),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", name="uq_calendar_feeds_user"),
        sa.UniqueConstraint("token_hash", name="uq_calendar_feeds_token_hash"),
    )
    op.add_column(
        "users", sa.Column("reminder_minutes", sa.Integer(), server_default="10", nullable=True)
    )
    op.create_check_constraint(
        "ck_users_reminder_minutes", "users", "reminder_minutes IN (5, 10, 15, 30)"
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_reminder_minutes", "users", type_="check")
    op.drop_column("users", "reminder_minutes")
    op.drop_table("calendar_feeds")
    op.drop_table("reminders_sent")
    op.drop_table("push_subscriptions")
