"""Practice items, their sources, reviews and generations (Phase 5, ADR 0025).

- practice_generations: one AI run for a topic (status, requested, produced, dropped counts
  by reason, provider, model, a readable error, its job). At most one queued or running per
  topic (a partial unique index). Cascades with its module and topic.
- practice_items: flashcards and short-answer questions (prompt 1-500 characters, answer
  1-1500, key_points 1-5 for short answers only), origin ai or user, status active,
  suspended or rejected (with a reason exactly when rejected). UNIQUE (user_id, topic_id,
  prompt_key) WHERE status <> 'rejected'. Deleting the topic sets topic_id null; deleting
  the module deletes them.
- practice_item_sources: the chunks an item cites, with their labels; PRIMARY KEY (item_id,
  chunk_id); both FKs composite with user_id, ON DELETE CASCADE.
- reviews: append-only (a trigger refuses UPDATE); grade 1-4, marked_by self or ai.

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _in(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def upgrade() -> None:
    op.create_table(
        "practice_generations",
        *_timestamps(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(10), server_default="queued", nullable=False),
        sa.Column("requested", sa.SmallInteger(), nullable=False),
        sa.Column("produced", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("dropped", JSONB(), server_default="{}", nullable=False),
        sa.Column("provider", sa.String(20), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["module_id", "user_id"], ["modules.id", "modules.user_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["topic_id", "module_id"], ["topics.id", "topics.module_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("id", "user_id", name="uq_practice_generations_id_user"),
        sa.CheckConstraint(
            _in("status", ("queued", "running", "succeeded", "failed")),
            name="ck_practice_generations_status",
        ),
        sa.CheckConstraint("requested BETWEEN 1 AND 12", name="ck_practice_generations_requested"),
        sa.CheckConstraint("produced >= 0", name="ck_practice_generations_produced"),
    )
    op.create_index(
        "uq_practice_generations_one_active",
        "practice_generations",
        ["topic_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_index(
        "ix_practice_generations_topic", "practice_generations", ["topic_id", "created_at"]
    )

    op.create_table(
        "practice_items",
        *_timestamps(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("key_points", JSONB(), nullable=True),
        sa.Column("origin", sa.String(10), nullable=False),
        sa.Column("status", sa.String(10), server_default="active", nullable=False),
        sa.Column("reject_reason", sa.String(20), nullable=True),
        sa.Column("provider", sa.String(20), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("generation_id", sa.Uuid(), nullable=True),
        sa.Column("prompt_key", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["module_id", "user_id"], ["modules.id", "modules.user_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["topic_id", "module_id"],
            ["topics.id", "topics.module_id"],
            ondelete="SET NULL (topic_id)",
        ),
        sa.ForeignKeyConstraint(
            ["generation_id", "user_id"],
            ["practice_generations.id", "practice_generations.user_id"],
            ondelete="SET NULL (generation_id)",
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_practice_items_id_user"),
        sa.CheckConstraint(
            _in("kind", ("flashcard", "short_answer")), name="ck_practice_items_kind"
        ),
        sa.CheckConstraint(_in("origin", ("ai", "user")), name="ck_practice_items_origin"),
        sa.CheckConstraint(
            _in("status", ("active", "suspended", "rejected")), name="ck_practice_items_status"
        ),
        sa.CheckConstraint(
            "char_length(prompt) BETWEEN 1 AND 500", name="ck_practice_items_prompt"
        ),
        sa.CheckConstraint(
            "char_length(answer) BETWEEN 1 AND 1500", name="ck_practice_items_answer"
        ),
        sa.CheckConstraint(
            "(kind = 'flashcard' AND key_points IS NULL) OR (kind = 'short_answer' "
            "AND key_points IS NOT NULL AND jsonb_typeof(key_points) = 'array' "
            "AND jsonb_array_length(key_points) BETWEEN 1 AND 5)",
            name="ck_practice_items_key_points",
        ),
        sa.CheckConstraint(
            "(status = 'rejected') = (reject_reason IS NOT NULL)",
            name="ck_practice_items_reject_reason",
        ),
        sa.CheckConstraint(
            "reject_reason IS NULL OR "
            + _in("reject_reason", ("wrong", "unclear", "not_in_source", "duplicate", "other")),
            name="ck_practice_items_reject_reasons",
        ),
        sa.CheckConstraint(
            "origin = 'user' OR (provider IS NOT NULL AND model IS NOT NULL)",
            name="ck_practice_items_ai_model",
        ),
        sa.CheckConstraint("char_length(prompt_key) = 64", name="ck_practice_items_prompt_key"),
    )
    op.create_index(
        "uq_practice_items_topic_prompt",
        "practice_items",
        ["user_id", "topic_id", "prompt_key"],
        unique=True,
        postgresql_where=sa.text("status <> 'rejected'"),
    )
    op.create_index("ix_practice_items_module", "practice_items", ["module_id", "created_at"])
    op.create_index("ix_practice_items_topic", "practice_items", ["topic_id"])

    op.create_table(
        "practice_item_sources",
        sa.Column("item_id", sa.Uuid(), primary_key=True),
        sa.Column("chunk_id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(5), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id", "user_id"],
            ["practice_items.id", "practice_items.user_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id", "user_id"], ["chunks.id", "chunks.user_id"], ondelete="CASCADE"
        ),
        sa.CheckConstraint("label ~ '^S[1-9][0-9]*$'", name="ck_practice_item_sources_label"),
    )
    op.create_index("ix_practice_item_sources_chunk", "practice_item_sources", ["chunk_id"])

    op.create_table(
        "reviews",
        *_timestamps(),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("grade", sa.SmallInteger(), nullable=False),
        sa.Column("marked_by", sa.String(10), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["item_id", "user_id"],
            ["practice_items.id", "practice_items.user_id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("grade BETWEEN 1 AND 4", name="ck_reviews_grade"),
        sa.CheckConstraint(_in("marked_by", ("self", "ai")), name="ck_reviews_marked_by"),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0", name="ck_reviews_duration_ms"
        ),
        sa.CheckConstraint(
            "answer_text IS NULL OR char_length(answer_text) <= 2000",
            name="ck_reviews_answer_text",
        ),
    )
    op.create_index("ix_reviews_user_item_at", "reviews", ["user_id", "item_id", "reviewed_at"])
    # Append-only: a review is never changed. Deletes stay possible, so a review still goes
    # with its item (and the item with its module).
    op.execute(
        """
        CREATE FUNCTION reviews_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'reviews are append-only' USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_reviews_append_only BEFORE UPDATE ON reviews "
        "FOR EACH ROW EXECUTE FUNCTION reviews_append_only()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_reviews_append_only ON reviews")
    op.execute("DROP FUNCTION IF EXISTS reviews_append_only()")
    op.drop_table("reviews")
    op.drop_table("practice_item_sources")
    op.drop_table("practice_items")
    op.drop_table("practice_generations")
