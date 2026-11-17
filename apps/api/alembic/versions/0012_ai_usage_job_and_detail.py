"""ai_usage: job_id, detail and the "truncated" outcome (decision 0007).

- job_id: the job that made the call, so a job counts its calls across retries and
  reschedules (the cap on calls per material). SET NULL when the job is deleted.
- detail: why a call failed (HTTP status and the provider's message, or what didn't
  validate), at most 300 characters. Never prompt or reply text.
- outcome "truncated": the reply hit the model's output limit.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ai_usage", sa.Column("job_id", sa.Uuid(), nullable=True))
    op.add_column("ai_usage", sa.Column("detail", sa.String(length=300), nullable=True))
    op.create_foreign_key(
        "fk_ai_usage_job", "ai_usage", "jobs", ["job_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index(
        "ix_ai_usage_job",
        "ai_usage",
        ["job_id"],
        postgresql_where=sa.text("job_id IS NOT NULL"),
    )
    op.drop_constraint("ck_ai_usage_outcome", "ai_usage", type_="check")
    op.create_check_constraint(
        "ck_ai_usage_outcome",
        "ai_usage",
        "outcome IN ('ok', 'rate_limited', 'error', 'invalid_json', 'timeout', 'truncated')",
    )


def downgrade() -> None:
    op.execute("UPDATE ai_usage SET outcome = 'error' WHERE outcome = 'truncated'")
    op.drop_constraint("ck_ai_usage_outcome", "ai_usage", type_="check")
    op.create_check_constraint(
        "ck_ai_usage_outcome",
        "ai_usage",
        "outcome IN ('ok', 'rate_limited', 'error', 'invalid_json', 'timeout')",
    )
    op.drop_index("ix_ai_usage_job", table_name="ai_usage")
    op.drop_constraint("fk_ai_usage_job", "ai_usage", type_="foreignkey")
    op.drop_column("ai_usage", "detail")
    op.drop_column("ai_usage", "job_id")
