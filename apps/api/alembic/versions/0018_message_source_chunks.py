"""message_sources.chunk_id: the passage an answer was given, for follow-ups.

"Explain that differently", "Give an example" and "Quiz me" reuse the previous answer's
sources with the same labels, so they need the exact passages, not just the pages.
- chunks gets UNIQUE (id, user_id), so the new composite FK can include user_id.
- message_sources.chunk_id: set to NULL when the chunk goes (a re-index replaces a
  material's chunks); the source then falls back to its page's first chunk.

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint("uq_chunks_id_user", "chunks", ["id", "user_id"])
    op.add_column("message_sources", sa.Column("chunk_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_message_sources_chunk",
        "message_sources",
        "chunks",
        ["chunk_id", "user_id"],
        ["id", "user_id"],
        ondelete="SET NULL (chunk_id)",
    )


def downgrade() -> None:
    op.drop_constraint("fk_message_sources_chunk", "message_sources", type_="foreignkey")
    op.drop_column("message_sources", "chunk_id")
    op.drop_constraint("uq_chunks_id_user", "chunks", type_="unique")
