"""ai_usage: one row per request to an AI provider (decision 0002).

No prompt or reply text, only provider, model, role, purpose, token counts, latency
and outcome. The LLM client counts these rows for its daily budgets.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_usage",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("purpose", sa.String(length=50), nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
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
        sa.CheckConstraint("role IN ('smart', 'bulk')", name="ck_ai_usage_role"),
        sa.CheckConstraint(
            "outcome IN ('ok', 'rate_limited', 'error', 'invalid_json')",
            name="ck_ai_usage_outcome",
        ),
        sa.CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND latency_ms >= 0",
            name="ck_ai_usage_counts",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_usage_budget", "ai_usage", ["user_id", "provider", "model", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_ai_usage_budget", table_name="ai_usage")
    op.drop_table("ai_usage")
