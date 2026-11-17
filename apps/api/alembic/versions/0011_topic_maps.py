"""Topic maps (decision 0006): proposals, cited pages, chunk links, the "long" AI role.

- topic_proposals: one per material (validated AI JSON + the model that answered).
- topic_pages: the pages each topic was drawn from, cited by the merge.
- chunk_topics: chunk ↔ topic links (method pages or similarity); composite FKs through
  module_id, so it needs UNIQUE (id, module_id) on chunks.
- ai_usage.role may now be "long" (whole documents in one prompt).
- Data: an extract_topics job for every indexed material that's eligible (allow_ai on;
  slides, notes, study guide, tutorial or outline) and has none queued.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # chunk_topics' composite FK needs this first.
    op.create_unique_constraint("uq_chunks_id_module", "chunks", ["id", "module_id"])
    op.create_table(
        "topic_pages",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=False),
        sa.Column("material_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
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
        sa.CheckConstraint("page_number >= 1", name="ck_topic_pages_number"),
        sa.ForeignKeyConstraint(
            ["material_id", "module_id"],
            ["materials.id", "materials.module_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id", "module_id"], ["topics.id", "topics.module_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["topic_id", "user_id"], ["topics.id", "topics.user_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("topic_id", "material_id", "page_number", name="uq_topic_pages"),
    )
    op.create_index(
        "ix_topic_pages_user_module", "topic_pages", ["user_id", "module_id"], unique=False
    )
    op.create_table(
        "topic_proposals",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.Column("material_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("topics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["material_id", "module_id"],
            ["materials.id", "materials.module_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["material_id", "user_id"], ["materials.id", "materials.user_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("material_id", name="uq_topic_proposals_material"),
    )
    op.create_index(
        "ix_topic_proposals_user_module", "topic_proposals", ["user_id", "module_id"], unique=False
    )
    op.create_table(
        "chunk_topics",
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("method", sa.String(length=20), nullable=False),
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
        sa.CheckConstraint("method IN ('pages', 'similarity')", name="ck_chunk_topics_method"),
        sa.CheckConstraint("score >= -1 AND score <= 1", name="ck_chunk_topics_score"),
        sa.ForeignKeyConstraint(
            ["chunk_id", "module_id"], ["chunks.id", "chunks.module_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["topic_id", "module_id"], ["topics.id", "topics.module_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chunk_id", "topic_id", name="uq_chunk_topics"),
    )
    op.create_index("ix_chunk_topics_module", "chunk_topics", ["module_id"], unique=False)
    op.create_index("ix_chunk_topics_topic", "chunk_topics", ["topic_id"], unique=False)
    op.drop_constraint("ck_ai_usage_role", "ai_usage", type_="check")
    op.create_check_constraint(
        "ck_ai_usage_role", "ai_usage", "role IN ('smart', 'bulk', 'vision', 'long')"
    )
    queue_extraction()


def queue_extraction() -> None:
    """Queue topic extraction for materials already indexed (data only)."""
    op.execute(
        """
        INSERT INTO jobs (id, user_id, kind, payload)
        SELECT gen_random_uuid(), m.user_id, 'extract_topics',
               jsonb_build_object('material_id', m.id::text, 'module_id', m.module_id::text)
        FROM materials m
        WHERE m.status = 'ready'
          AND m.allow_ai
          AND m.kind IN ('slides', 'notes', 'study_guide', 'tutorial', 'outline')
          AND NOT EXISTS (
            SELECT 1 FROM jobs j
            WHERE j.user_id = m.user_id
              AND j.kind = 'extract_topics'
              AND j.status IN ('queued', 'running')
              AND j.payload ->> 'material_id' = m.id::text
          )
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM jobs WHERE kind IN ('extract_topics', 'merge_topics', 'link_topics') "
        "AND status IN ('queued', 'running')"
    )
    op.execute("UPDATE ai_usage SET role = 'smart' WHERE role = 'long'")
    op.drop_constraint("ck_ai_usage_role", "ai_usage", type_="check")
    op.create_check_constraint(
        "ck_ai_usage_role", "ai_usage", "role IN ('smart', 'bulk', 'vision')"
    )
    op.drop_index("ix_chunk_topics_topic", table_name="chunk_topics")
    op.drop_index("ix_chunk_topics_module", table_name="chunk_topics")
    op.drop_table("chunk_topics")
    op.drop_index("ix_topic_proposals_user_module", table_name="topic_proposals")
    op.drop_table("topic_proposals")
    op.drop_index("ix_topic_pages_user_module", table_name="topic_pages")
    op.drop_table("topic_pages")
    op.drop_constraint("uq_chunks_id_module", "chunks", type_="unique")
