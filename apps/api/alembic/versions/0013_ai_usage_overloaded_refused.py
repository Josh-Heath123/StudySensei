"""ai_usage: the "overloaded" and "refused" outcomes (decision 0008).

- overloaded: a 503 ("high demand"), turned away before running like a 429.
- refused: the model declined the content (a safety or content filter, or an empty reply).

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "('ok', 'rate_limited', 'error', 'invalid_json', 'timeout', 'truncated')"
NEW = (
    "('ok', 'rate_limited', 'error', 'invalid_json', 'timeout', 'truncated', "
    "'overloaded', 'refused')"
)


def upgrade() -> None:
    op.drop_constraint("ck_ai_usage_outcome", "ai_usage", type_="check")
    op.create_check_constraint("ck_ai_usage_outcome", "ai_usage", f"outcome IN {NEW}")


def downgrade() -> None:
    op.execute("UPDATE ai_usage SET outcome = 'error' WHERE outcome IN ('overloaded', 'refused')")
    op.drop_constraint("ck_ai_usage_outcome", "ai_usage", type_="check")
    op.create_check_constraint("ck_ai_usage_outcome", "ai_usage", f"outcome IN {OLD}")
