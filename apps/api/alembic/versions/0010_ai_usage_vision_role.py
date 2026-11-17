"""ai_usage: add the "vision" role.

Requests with an image now go to their own role (scanned pages, figure slides), and
their usage rows say so.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_ai_usage_role", "ai_usage", type_="check")
    op.create_check_constraint(
        "ck_ai_usage_role", "ai_usage", "role IN ('smart', 'bulk', 'vision')"
    )


def downgrade() -> None:
    # Before this role existed, image requests ran under "smart".
    op.execute("UPDATE ai_usage SET role = 'smart' WHERE role = 'vision'")
    op.drop_constraint("ck_ai_usage_role", "ai_usage", type_="check")
    op.create_check_constraint("ck_ai_usage_role", "ai_usage", "role IN ('smart', 'bulk')")
