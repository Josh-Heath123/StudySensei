"""Academic structure: modules, topics, assessments, assessment_topics, tasks.

User isolation: children reference parents through composite FKs that include
user_id or module_id, so Postgres rejects any cross-user link.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "modules",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("colour", sa.String(length=7), nullable=False),
        sa.Column("semester", sa.String(length=20), nullable=True),
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
        sa.CheckConstraint("colour ~ '^#[0-9A-Fa-f]{6}$'", name="ck_modules_colour_hex"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "user_id", name="uq_modules_id_user"),
        sa.UniqueConstraint("user_id", "code", name="uq_modules_user_code"),
    )
    op.create_table(
        "assessments",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("weight", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="upcoming", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.CheckConstraint(
            "kind IN ('exam', 'test', 'assignment', 'quiz', 'project', 'other')",
            name="ck_assessments_kind",
        ),
        sa.CheckConstraint(
            "status IN ('upcoming', 'completed', 'cancelled')", name="ck_assessments_status"
        ),
        sa.CheckConstraint(
            "weight IS NULL OR weight BETWEEN 0 AND 100", name="ck_assessments_weight"
        ),
        sa.ForeignKeyConstraint(
            ["module_id", "user_id"], ["modules.id", "modules.user_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "module_id", name="uq_assessments_id_module"),
        sa.UniqueConstraint("id", "user_id", name="uq_assessments_id_user"),
    )
    op.create_index("ix_assessments_module", "assessments", ["module_id"], unique=False)
    op.create_table(
        "topics",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("source", sa.String(length=10), server_default="user", nullable=False),
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
        sa.CheckConstraint("source IN ('user', 'ai')", name="ck_topics_source"),
        sa.CheckConstraint("parent_id IS NULL OR parent_id <> id", name="ck_topics_not_own_parent"),
        sa.ForeignKeyConstraint(
            ["module_id", "user_id"], ["modules.id", "modules.user_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["parent_id", "module_id"], ["topics.id", "topics.module_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "module_id", name="uq_topics_id_module"),
        sa.UniqueConstraint("id", "user_id", name="uq_topics_id_user"),
    )
    op.create_index("ix_topics_module_parent", "topics", ["module_id", "parent_id"], unique=False)
    op.create_table(
        "assessment_topics",
        sa.Column("assessment_id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assessment_id", "module_id"],
            ["assessments.id", "assessments.module_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id", "module_id"], ["topics.id", "topics.module_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("assessment_id", "topic_id"),
    )
    op.create_index("ix_assessment_topics_topic", "assessment_topics", ["topic_id"], unique=False)
    op.create_table(
        "tasks",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="todo", nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.CheckConstraint("status IN ('todo', 'in_progress', 'done')", name="ck_tasks_status"),
        sa.ForeignKeyConstraint(
            ["assessment_id", "module_id"],
            ["assessments.id", "assessments.module_id"],
            ondelete="SET NULL (assessment_id)",
        ),
        sa.ForeignKeyConstraint(
            ["module_id", "user_id"], ["modules.id", "modules.user_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "user_id", name="uq_tasks_id_user"),
    )
    op.create_index("ix_tasks_module", "tasks", ["module_id"], unique=False)
    op.create_index("ix_tasks_assessment", "tasks", ["assessment_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_tasks_assessment", table_name="tasks")
    op.drop_index("ix_tasks_module", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index("ix_assessment_topics_topic", table_name="assessment_topics")
    op.drop_table("assessment_topics")
    op.drop_index("ix_topics_module_parent", table_name="topics")
    op.drop_table("topics")
    op.drop_index("ix_assessments_module", table_name="assessments")
    op.drop_table("assessments")
    op.drop_table("modules")
