"""The AI marking a review was graded with (Phase 5 task 4, ADR 0029).

- reviews.ai_marking: JSONB, null unless the student asked the AI to check a short answer
  before grading it (``schemas.practice.AIMarking``: coverage, verdict, suggested grade,
  feedback, model). A check that marked_by "ai" comes with it. The append-only trigger
  stays.

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("reviews", sa.Column("ai_marking", JSONB(none_as_null=True), nullable=True))
    op.create_check_constraint(
        "ck_reviews_ai_marking", "reviews", "marked_by <> 'ai' OR ai_marking IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_constraint("ck_reviews_ai_marking", "reviews", type_="check")
    op.drop_column("reviews", "ai_marking")
