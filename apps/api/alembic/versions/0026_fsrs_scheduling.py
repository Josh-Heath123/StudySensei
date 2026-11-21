"""FSRS scheduling: item states, review snapshots and the practice settings (Phase 5,
ADR 0026).

- practice_item_states: one row per reviewed item (no row: new). PRIMARY KEY item_id; a
  composite FK (item_id, user_id) to practice_items, cascading; state learning, review or
  relearning; step, stability (> 0), difficulty (1-10), due (after last_review_at), reps
  (>= 1), lapses (>= 0); an index on (user_id, due) for the queue.
- reviews: state_before and state_after (JSONB snapshots), scheduled_days, desired_retention
  and fsrs_version, all null on reviews from before this migration. The append-only trigger
  stays.
- users: practice_new_per_day (0-200, default 20) and practice_desired_retention (0.80-0.97,
  default 0.90).

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "practice_item_states",
        sa.Column("item_id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(10), nullable=False),
        sa.Column("step", sa.SmallInteger(), nullable=True),
        sa.Column("stability", sa.Double(), nullable=False),
        sa.Column("difficulty", sa.Double(), nullable=False),
        sa.Column("due", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_review_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reps", sa.Integer(), nullable=False),
        sa.Column("lapses", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id", "user_id"],
            ["practice_items.id", "practice_items.user_id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "state IN ('learning', 'review', 'relearning')", name="ck_practice_item_states_state"
        ),
        sa.CheckConstraint("step IS NULL OR step >= 0", name="ck_practice_item_states_step"),
        sa.CheckConstraint("stability > 0", name="ck_practice_item_states_stability"),
        sa.CheckConstraint(
            "difficulty BETWEEN 1 AND 10", name="ck_practice_item_states_difficulty"
        ),
        sa.CheckConstraint("reps >= 1 AND lapses >= 0", name="ck_practice_item_states_counts"),
        sa.CheckConstraint("due > last_review_at", name="ck_practice_item_states_due"),
    )
    op.create_index("ix_practice_item_states_user_due", "practice_item_states", ["user_id", "due"])
    op.add_column("reviews", sa.Column("state_before", JSONB(), nullable=True))
    op.add_column("reviews", sa.Column("state_after", JSONB(), nullable=True))
    op.add_column("reviews", sa.Column("scheduled_days", sa.Integer(), nullable=True))
    op.add_column("reviews", sa.Column("desired_retention", sa.Double(), nullable=True))
    op.add_column("reviews", sa.Column("fsrs_version", sa.String(20), nullable=True))
    op.add_column(
        "users",
        sa.Column("practice_new_per_day", sa.Integer(), server_default="20", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("practice_desired_retention", sa.Double(), server_default="0.9", nullable=False),
    )
    op.create_check_constraint(
        "ck_users_practice_new_per_day", "users", "practice_new_per_day BETWEEN 0 AND 200"
    )
    op.create_check_constraint(
        "ck_users_practice_desired_retention",
        "users",
        "practice_desired_retention BETWEEN 0.80 AND 0.97",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_practice_desired_retention", "users", type_="check")
    op.drop_constraint("ck_users_practice_new_per_day", "users", type_="check")
    op.drop_column("users", "practice_desired_retention")
    op.drop_column("users", "practice_new_per_day")
    for column in (
        "fsrs_version",
        "desired_retention",
        "scheduled_days",
        "state_after",
        "state_before",
    ):
        op.drop_column("reviews", column)
    op.drop_table("practice_item_states")
