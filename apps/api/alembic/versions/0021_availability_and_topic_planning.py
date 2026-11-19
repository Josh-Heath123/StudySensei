"""Availability, planning settings, and workload and confidence per topic (Phase 4).

- users.timezone (IANA, default Africa/Johannesburg) and users.daily_study_cap_minutes
  (default 180, 15 to 1440).
- availability_rules: weekly windows in minutes after local midnight; no overlaps per user
  and weekday (an exclusion constraint, so btree_gist).
- availability_exceptions: one per user and date; unavailable all day, or its own windows.
- topics.estimated_minutes (the student's override, 5 to 6000) and topics.confidence
  (1 to 5, self-reported); both nullable.

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-20
"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WINDOW_CHECK = "start_minute >= 0 AND start_minute < end_minute AND end_minute <= 1440"


def _timestamps() -> list[sa.Column[datetime]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.add_column(
        "users",
        sa.Column("timezone", sa.String(64), server_default="Africa/Johannesburg", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("daily_study_cap_minutes", sa.Integer(), server_default="180", nullable=False),
    )
    op.create_check_constraint(
        "ck_users_daily_study_cap", "users", "daily_study_cap_minutes BETWEEN 15 AND 1440"
    )

    op.add_column("topics", sa.Column("estimated_minutes", sa.Integer(), nullable=True))
    op.add_column("topics", sa.Column("confidence", sa.SmallInteger(), nullable=True))
    op.create_check_constraint("ck_topics_confidence", "topics", "confidence BETWEEN 1 AND 5")
    op.create_check_constraint(
        "ck_topics_estimated_minutes", "topics", "estimated_minutes BETWEEN 5 AND 6000"
    )

    op.create_table(
        "availability_rules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("start_minute", sa.Integer(), nullable=False),
        sa.Column("end_minute", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("id", "user_id", name="uq_availability_rules_id_user"),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_availability_rules_weekday"),
        sa.CheckConstraint(WINDOW_CHECK, name="ck_availability_rules_window"),
        postgresql.ExcludeConstraint(
            ("user_id", "="),
            ("weekday", "="),
            (sa.literal_column("int4range(start_minute, end_minute)"), "&&"),
            name="ex_availability_rules_overlap",
            using="gist",
        ),
    )

    op.create_table(
        "availability_exceptions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("unavailable", sa.Boolean(), nullable=False),
        sa.Column(
            "windows", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column("note", sa.String(200), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("id", "user_id", name="uq_availability_exceptions_id_user"),
        sa.UniqueConstraint("user_id", "date", name="uq_availability_exceptions_date"),
        sa.CheckConstraint(
            "unavailable = (jsonb_array_length(windows) = 0)",
            name="ck_availability_exceptions_windows",
        ),
    )
    op.create_index(
        "ix_availability_exceptions_user_date", "availability_exceptions", ["user_id", "date"]
    )


def downgrade() -> None:
    op.drop_index("ix_availability_exceptions_user_date", "availability_exceptions")
    op.drop_table("availability_exceptions")
    op.drop_table("availability_rules")
    op.drop_constraint("ck_topics_estimated_minutes", "topics", type_="check")
    op.drop_constraint("ck_topics_confidence", "topics", type_="check")
    op.drop_column("topics", "confidence")
    op.drop_column("topics", "estimated_minutes")
    op.drop_constraint("ck_users_daily_study_cap", "users", type_="check")
    op.drop_column("users", "daily_study_cap_minutes")
    op.drop_column("users", "timezone")
    # btree_gist stays: other tables may come to use it, and dropping it is never needed.
