"""Extracted text per page (material_pages), and extraction for materials already uploaded.

- material_pages: one row per PDF page, slide or document section, with its text,
  character count and an is_scanned flag (almost no text layer).
- materials.scanned_page_count: how many pages are scanned.
- Data: the count_pages job is replaced by extract_text. Queued count_pages jobs
  become extract_text, and every other material gets an extract_text job, so files
  uploaded before this change are extracted too.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "material_pages",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("material_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("is_scanned", sa.Boolean(), nullable=False),
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
        sa.CheckConstraint("char_count = char_length(text)", name="ck_material_pages_char_count"),
        sa.CheckConstraint("page_number >= 1", name="ck_material_pages_number"),
        sa.ForeignKeyConstraint(
            ["material_id", "user_id"],
            ["materials.id", "materials.user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("material_id", "page_number", name="uq_material_pages_number"),
    )
    op.add_column("materials", sa.Column("scanned_page_count", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_materials_scanned_pages",
        "materials",
        "scanned_page_count IS NULL OR scanned_page_count BETWEEN 0 AND page_count",
    )

    queue_extraction()


def queue_extraction() -> None:
    """Replace count_pages with extract_text and queue it for every material (data only)."""
    # count_pages is gone: anything still waiting for it is extracted instead.
    op.execute(
        "UPDATE jobs SET kind = 'extract_text' "
        "WHERE kind = 'count_pages' AND status IN ('queued', 'running')"
    )
    # Every other material is extracted too (it only had its pages counted).
    op.execute(
        """
        INSERT INTO jobs (id, user_id, kind, payload)
        SELECT gen_random_uuid(), m.user_id, 'extract_text',
               jsonb_build_object('material_id', m.id::text)
        FROM materials m
        WHERE NOT EXISTS (
            SELECT 1 FROM jobs j
            WHERE j.user_id = m.user_id
              AND j.kind = 'extract_text'
              AND j.status IN ('queued', 'running')
              AND j.payload ->> 'material_id' = m.id::text
        )
        """
    )
    op.execute("UPDATE materials SET status = 'uploaded', error = NULL")


def downgrade() -> None:
    op.execute(
        "UPDATE jobs SET kind = 'count_pages' "
        "WHERE kind = 'extract_text' AND status IN ('queued', 'running')"
    )
    op.drop_constraint("ck_materials_scanned_pages", "materials", type_="check")
    op.drop_column("materials", "scanned_page_count")
    op.drop_table("material_pages")
