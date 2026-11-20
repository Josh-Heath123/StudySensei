"""Pinned plan blocks and the "move" trigger (Phase 4, decision 0022).

- plan_blocks.pinned: the student moved this block; re-plans carry it forward at its time.
- plan_versions.trigger also allows 'move'.

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = (
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
NEW = (*OLD, "move")


def _in(values: Sequence[str]) -> str:
    return f"trigger IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.add_column(
        "plan_blocks", sa.Column("pinned", sa.Boolean(), server_default="false", nullable=False)
    )
    op.drop_constraint("ck_plan_versions_trigger", "plan_versions", type_="check")
    op.create_check_constraint("ck_plan_versions_trigger", "plan_versions", _in(NEW))


def downgrade() -> None:
    op.execute("DELETE FROM plan_versions WHERE trigger = 'move'")
    op.drop_constraint("ck_plan_versions_trigger", "plan_versions", type_="check")
    op.create_check_constraint("ck_plan_versions_trigger", "plan_versions", _in(OLD))
    op.drop_column("plan_blocks", "pinned")
