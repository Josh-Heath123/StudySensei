"""Chunks for search, and indexing for materials already extracted (decision 0005).

- chunks: one row per piece of a page, with its embedding (vector(384), no vector
  index: search scans a module's chunks exactly) and a generated english tsvector
  with a GIN index. Rows cascade from their material and from their page.
- Data: materials are "ready" only once indexed. Every material already extracted
  goes back to processing and gets an index_material job.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chunks",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.Column("material_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', text)", persisted=True),
            nullable=False,
        ),
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
        sa.CheckConstraint("position >= 0", name="ck_chunks_position"),
        sa.CheckConstraint("token_count > 0", name="ck_chunks_token_count"),
        sa.ForeignKeyConstraint(
            ["material_id", "user_id"],
            ["materials.id", "materials.user_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["material_id", "module_id"],
            ["materials.id", "materials.module_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["material_id", "page_number"],
            ["material_pages.material_id", "material_pages.page_number"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("material_id", "page_number", "position", name="uq_chunks_position"),
    )
    op.create_index("ix_chunks_user_module", "chunks", ["user_id", "module_id"])
    op.create_index("ix_chunks_tsv", "chunks", ["tsv"], postgresql_using="gin")

    queue_indexing()


def queue_indexing() -> None:
    """Index every material whose text is already extracted (data only)."""
    op.execute(
        """
        INSERT INTO jobs (id, user_id, kind, payload)
        SELECT gen_random_uuid(), m.user_id, 'index_material',
               jsonb_build_object('material_id', m.id::text)
        FROM materials m
        WHERE m.status = 'ready'
          AND NOT EXISTS (
            SELECT 1 FROM jobs j
            WHERE j.user_id = m.user_id
              AND j.kind = 'index_material'
              AND j.status IN ('queued', 'running')
              AND j.payload ->> 'material_id' = m.id::text
          )
        """
    )
    op.execute("UPDATE materials SET status = 'processing' WHERE status = 'ready'")


def downgrade() -> None:
    # Without chunks there's nothing to wait for: indexing materials count as extracted.
    op.execute(
        """
        UPDATE materials m SET status = 'ready'
        WHERE m.status = 'processing' AND m.error IS NULL
          AND EXISTS (
            SELECT 1 FROM jobs j
            WHERE j.user_id = m.user_id AND j.kind = 'index_material'
              AND j.status IN ('queued', 'running')
              AND j.payload ->> 'material_id' = m.id::text
          )
        """
    )
    op.execute("DELETE FROM jobs WHERE kind = 'index_material' AND status IN ('queued', 'running')")
    op.drop_index("ix_chunks_tsv", table_name="chunks")
    op.drop_index("ix_chunks_user_module", table_name="chunks")
    op.drop_table("chunks")
