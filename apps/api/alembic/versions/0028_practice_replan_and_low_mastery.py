"""Mastery in the plan (Phase 5 task 5, ADR 0031).

- plan_versions.trigger also allows 'practice': a review queues a re-plan 15 minutes later.
- plan_blocks.reason also allows 'low_mastery': a unit whose estimated mastery is below 0.5.

Down deletes the versions a practice re-plan wrote and turns low_mastery blocks back into
low_confidence ones (the nearest reason the old check allows); their text is kept.

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_TRIGGERS = (
    "initial",
    "skip",
    "finish",
    "assessment",
    "topic",
    "availability",
    "material",
    "nightly",
    "manual",
    "move",
)
NEW_TRIGGERS = (*OLD_TRIGGERS, "practice")
OLD_REASONS = ("final_review", "spacing", "no_estimate", "low_confidence", "urgency", "workload")
NEW_REASONS = (*OLD_REASONS, "low_mastery")


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.drop_constraint("ck_plan_versions_trigger", "plan_versions", type_="check")
    op.create_check_constraint(
        "ck_plan_versions_trigger", "plan_versions", _in("trigger", NEW_TRIGGERS)
    )
    op.drop_constraint("ck_plan_blocks_reason", "plan_blocks", type_="check")
    op.create_check_constraint("ck_plan_blocks_reason", "plan_blocks", _in("reason", NEW_REASONS))


def downgrade() -> None:
    op.execute("DELETE FROM plan_versions WHERE trigger = 'practice'")
    op.execute("UPDATE plan_blocks SET reason = 'low_confidence' WHERE reason = 'low_mastery'")
    op.drop_constraint("ck_plan_blocks_reason", "plan_blocks", type_="check")
    op.create_check_constraint("ck_plan_blocks_reason", "plan_blocks", _in("reason", OLD_REASONS))
    op.drop_constraint("ck_plan_versions_trigger", "plan_versions", type_="check")
    op.create_check_constraint(
        "ck_plan_versions_trigger", "plan_versions", _in("trigger", OLD_TRIGGERS)
    )
