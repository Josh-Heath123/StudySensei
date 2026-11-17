"""ai_usage: add the "timeout" outcome.

A request that timed out (connecting, or waiting for the reply) is logged as "timeout"
rather than "error", and still counts against the daily budget.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_ai_usage_outcome", "ai_usage", type_="check")
    op.create_check_constraint(
        "ck_ai_usage_outcome",
        "ai_usage",
        "outcome IN ('ok', 'rate_limited', 'error', 'invalid_json', 'timeout')",
    )


def downgrade() -> None:
    op.execute("UPDATE ai_usage SET outcome = 'error' WHERE outcome = 'timeout'")
    op.drop_constraint("ck_ai_usage_outcome", "ai_usage", type_="check")
    op.create_check_constraint(
        "ck_ai_usage_outcome",
        "ai_usage",
        "outcome IN ('ok', 'rate_limited', 'error', 'invalid_json')",
    )
