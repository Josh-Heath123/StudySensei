"""Quizzes in messages; deleting a study session deletes its tutor conversation.

- messages.quiz (JSONB): a "Quiz me" answer, validated against app/schemas/tutor.py Quiz
  before it's stored, its questions already filtered to the answer's sources.
- messages.quiz_answers (JSONB): the student's pick for each question (null until
  answered). Grading is done by code, never by the model.
- conversations' study-session FK: ON DELETE CASCADE instead of SET NULL. A conversation
  whose session was deleted could no longer be reached in the app; when the student
  removes a study record, the conversation, its messages and its sources go with it.
  Conversations orphaned by an earlier delete are left alone: they look exactly like the
  ones made without a session (the API allows that, and the CLI's stored runs do it), so
  no row could be told apart safely.

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_FK = "conversations_study_session_id_module_id_fkey"
NEW_FK = "fk_conversations_study_session"


def upgrade() -> None:
    op.add_column("messages", sa.Column("quiz", postgresql.JSONB(), nullable=True))
    op.add_column("messages", sa.Column("quiz_answers", postgresql.JSONB(), nullable=True))
    op.drop_constraint(OLD_FK, "conversations", type_="foreignkey")
    op.create_foreign_key(
        NEW_FK,
        "conversations",
        "study_sessions",
        ["study_session_id", "module_id"],
        ["id", "module_id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(NEW_FK, "conversations", type_="foreignkey")
    op.create_foreign_key(
        OLD_FK,
        "conversations",
        "study_sessions",
        ["study_session_id", "module_id"],
        ["id", "module_id"],
        ondelete="SET NULL (study_session_id)",
    )
    op.drop_column("messages", "quiz_answers")
    op.drop_column("messages", "quiz")
