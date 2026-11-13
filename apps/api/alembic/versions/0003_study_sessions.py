"""Study sessions: study_sessions, session_events, session_topic_ratings.

session_events is an append-only log keyed by (user_id, client id); the totals on
study_sessions are rebuilt from it. A partial unique index allows one open
session per user. Children use composite FKs, as in 0002.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "study_sessions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=True),
        sa.Column("plan_block_id", sa.Uuid(), nullable=True),
        sa.Column("state", sa.String(length=10), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active_seconds", sa.Double(), nullable=False),
        sa.Column("break_seconds", sa.Double(), nullable=False),
        sa.Column("focus_rating", sa.SmallInteger(), nullable=True),
        sa.Column("covered_notes", sa.Text(), nullable=True),
        sa.Column("reflected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(state = 'ended') = (ended_at IS NOT NULL)", name="ck_study_sessions_ended"
        ),
        sa.CheckConstraint(
            "reflected_at IS NULL OR state = 'ended'", name="ck_study_sessions_reflect_ended"
        ),
        sa.CheckConstraint(
            "state IN ('active', 'paused', 'on_break', 'ended')", name="ck_study_sessions_state"
        ),
        sa.CheckConstraint(
            "active_seconds >= 0 AND break_seconds >= 0", name="ck_study_sessions_totals"
        ),
        sa.CheckConstraint(
            "focus_rating IS NULL OR focus_rating BETWEEN 1 AND 5", name="ck_study_sessions_focus"
        ),
        sa.ForeignKeyConstraint(
            ["module_id", "user_id"], ["modules.id", "modules.user_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["topic_id", "module_id"],
            ["topics.id", "topics.module_id"],
            ondelete="SET NULL (topic_id)",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "module_id", name="uq_study_sessions_id_module"),
        sa.UniqueConstraint("id", "user_id", name="uq_study_sessions_id_user"),
    )
    op.create_index(
        "ix_study_sessions_module_started",
        "study_sessions",
        ["module_id", "started_at"],
        unique=False,
    )
    op.create_index(
        "uq_study_sessions_one_active",
        "study_sessions",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
    )
    op.create_table(
        "session_events",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=12), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "type IN ('start', 'pause', 'resume', 'break_start', 'break_end', 'end')",
            name="ck_session_events_type",
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "user_id"],
            ["study_sessions.id", "study_sessions.user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "id"),
    )
    op.create_index(
        "ix_session_events_session_time",
        "session_events",
        ["session_id", "occurred_at", "seq"],
        unique=False,
    )
    op.create_table(
        "session_topic_ratings",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.Column("confidence", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint(
            "confidence BETWEEN 1 AND 5", name="ck_session_topic_ratings_confidence"
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "module_id"],
            ["study_sessions.id", "study_sessions.module_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id", "module_id"], ["topics.id", "topics.module_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("session_id", "topic_id"),
    )
    op.create_index(
        "ix_session_topic_ratings_topic", "session_topic_ratings", ["topic_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_session_topic_ratings_topic", table_name="session_topic_ratings")
    op.drop_table("session_topic_ratings")
    op.drop_index("ix_session_events_session_time", table_name="session_events")
    op.drop_table("session_events")
    op.drop_index(
        "uq_study_sessions_one_active",
        table_name="study_sessions",
        postgresql_where=sa.text("ended_at IS NULL"),
    )
    op.drop_index("ix_study_sessions_module_started", table_name="study_sessions")
    op.drop_table("study_sessions")
