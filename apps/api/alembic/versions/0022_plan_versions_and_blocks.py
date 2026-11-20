"""Plan versions and blocks, and re-plan coalescing (Phase 4, decision 0021).

- plan_versions: one per re-plan that changed something; number from 1 per user, the trigger,
  a code-written summary, generated_at and checked_at, days, and the feasibility report.
- plan_blocks: a version's blocks with their texts, status and fixed flag; composite FKs on
  (..., user_id) to plan_versions, modules, assessments and topics.
- study_sessions (plan_block_id, user_id) -> plan_blocks (id, user_id), ON DELETE SET NULL
  (plan_block_id) only, so user_id stays (Postgres 15+).
- jobs: at most one queued "replan" job per user (a partial unique index), so triggers
  coalesce.

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-21
"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TRIGGERS = (
    "initial",
    "skip",
    "finish",
    "assessment",
    "topic",
    "availability",
    "material",
    "nightly",
    "manual",
)


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


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
    op.create_table(
        "plan_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("days", sa.SmallInteger(), nullable=False),
        sa.Column("report", postgresql.JSONB(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("id", "user_id", name="uq_plan_versions_id_user"),
        sa.UniqueConstraint("user_id", "number", name="uq_plan_versions_user_number"),
        sa.CheckConstraint("number >= 1", name="ck_plan_versions_number"),
        sa.CheckConstraint(_in("trigger", TRIGGERS), name="ck_plan_versions_trigger"),
        sa.CheckConstraint("days BETWEEN 1 AND 62", name="ck_plan_versions_days"),
    )

    op.create_table(
        "plan_blocks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("reason", sa.String(20), nullable=False),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("reason_text", sa.Text(), nullable=False),
        sa.Column("method_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(10), server_default="planned", nullable=False),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fixed", sa.Boolean(), server_default="false", nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["version_id", "user_id"],
            ["plan_versions.id", "plan_versions.user_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["module_id", "user_id"], ["modules.id", "modules.user_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id", "user_id"],
            ["assessments.id", "assessments.user_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id", "user_id"], ["topics.id", "topics.user_id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_plan_blocks_id_user"),
        sa.CheckConstraint("end_at > start_at", name="ck_plan_blocks_times"),
        sa.CheckConstraint("kind IN ('study', 'review')", name="ck_plan_blocks_kind"),
        sa.CheckConstraint(
            _in(
                "reason",
                (
                    "final_review",
                    "spacing",
                    "no_estimate",
                    "low_confidence",
                    "urgency",
                    "workload",
                ),
            ),
            name="ck_plan_blocks_reason",
        ),
        sa.CheckConstraint(
            _in("method", ("mixed_review", "first_pass", "active_recall", "practice")),
            name="ck_plan_blocks_method",
        ),
        sa.CheckConstraint(
            _in("status", ("planned", "done", "skipped", "missed")), name="ck_plan_blocks_status"
        ),
        sa.CheckConstraint("(kind = 'review') = (topic_id IS NULL)", name="ck_plan_blocks_topic"),
    )
    op.create_index("ix_plan_blocks_user_start", "plan_blocks", ["user_id", "start_at"])
    op.create_index("ix_plan_blocks_version", "plan_blocks", ["version_id"])

    # A session's block must be the same user's; deleting the block keeps the session.
    op.execute(
        "ALTER TABLE study_sessions ADD CONSTRAINT "
        "fk_study_sessions_plan_block_id_user_id_plan_blocks "
        "FOREIGN KEY (plan_block_id, user_id) REFERENCES plan_blocks (id, user_id) "
        "ON DELETE SET NULL (plan_block_id)"
    )

    op.create_index(
        "uq_jobs_one_queued_replan",
        "jobs",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'replan' AND status = 'queued'"),
    )


def downgrade() -> None:
    op.drop_index("uq_jobs_one_queued_replan", "jobs")
    op.drop_constraint(
        "fk_study_sessions_plan_block_id_user_id_plan_blocks", "study_sessions", type_="foreignkey"
    )
    op.drop_index("ix_plan_blocks_version", "plan_blocks")
    op.drop_index("ix_plan_blocks_user_start", "plan_blocks")
    op.drop_table("plan_blocks")
    op.drop_table("plan_versions")
