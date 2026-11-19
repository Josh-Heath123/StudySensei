"""Academic structure: modules, topic trees, assessments and assignment tasks.

User isolation is enforced by Postgres, not just by query filters:
every user-owned table has UNIQUE (id, user_id), and children point at their
parent with a composite foreign key that includes user_id (or module_id).
A row can therefore never reference a parent owned by a different user.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampedBase

TOPIC_SOURCES = ("user", "ai")
ASSESSMENT_KINDS = ("exam", "test", "assignment", "quiz", "project", "other")
ASSESSMENT_STATUSES = ("upcoming", "completed", "cancelled")
TASK_STATUSES = ("todo", "in_progress", "done")


def _in(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


class Module(TimestampedBase):
    __tablename__ = "modules"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_modules_id_user"),
        UniqueConstraint("user_id", "code", name="uq_modules_user_code"),
        CheckConstraint("colour ~ '^#[0-9A-Fa-f]{6}$'", name="ck_modules_colour_hex"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(200))
    colour: Mapped[str] = mapped_column(String(7))
    semester: Mapped[str | None] = mapped_column(String(20))


class Topic(TimestampedBase):
    __tablename__ = "topics"
    __table_args__ = (
        ForeignKeyConstraint(
            ["module_id", "user_id"], ["modules.id", "modules.user_id"], ondelete="CASCADE"
        ),
        # A parent must live in the same module (and so belong to the same user).
        ForeignKeyConstraint(
            ["parent_id", "module_id"], ["topics.id", "topics.module_id"], ondelete="CASCADE"
        ),
        UniqueConstraint("id", "user_id", name="uq_topics_id_user"),
        UniqueConstraint("id", "module_id", name="uq_topics_id_module"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="ck_topics_not_own_parent"),
        CheckConstraint(_in("source", TOPIC_SOURCES), name="ck_topics_source"),
        CheckConstraint("confidence BETWEEN 1 AND 5", name="ck_topics_confidence"),
        CheckConstraint("estimated_minutes BETWEEN 5 AND 6000", name="ck_topics_estimated_minutes"),
        Index("ix_topics_module_parent", "module_id", "parent_id"),
    )

    user_id: Mapped[uuid.UUID]
    module_id: Mapped[uuid.UUID]
    parent_id: Mapped[uuid.UUID | None]
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    source: Mapped[str] = mapped_column(String(10), default="user", server_default="user")
    # Planning (migration 0021). The student's own workload figure: null means use the
    # estimate from the topic's pages (computed, never stored; services/planning/workload.py).
    estimated_minutes: Mapped[int | None] = mapped_column(Integer)
    # Starting confidence, 1 to 5, self-reported (never inferred by AI); null is not rated.
    confidence: Mapped[int | None] = mapped_column(SmallInteger)


class Assessment(TimestampedBase):
    __tablename__ = "assessments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["module_id", "user_id"], ["modules.id", "modules.user_id"], ondelete="CASCADE"
        ),
        UniqueConstraint("id", "user_id", name="uq_assessments_id_user"),
        UniqueConstraint("id", "module_id", name="uq_assessments_id_module"),
        CheckConstraint(_in("kind", ASSESSMENT_KINDS), name="ck_assessments_kind"),
        CheckConstraint(_in("status", ASSESSMENT_STATUSES), name="ck_assessments_status"),
        CheckConstraint("weight IS NULL OR weight BETWEEN 0 AND 100", name="ck_assessments_weight"),
        Index("ix_assessments_module", "module_id"),
    )

    user_id: Mapped[uuid.UUID]
    module_id: Mapped[uuid.UUID]
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    weight: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    status: Mapped[str] = mapped_column(String(20), default="upcoming", server_default="upcoming")
    notes: Mapped[str | None] = mapped_column(Text)


class AssessmentTopic(Base):
    """Which topics an assessment covers. Both sides must be in the same module."""

    __tablename__ = "assessment_topics"
    __table_args__ = (
        ForeignKeyConstraint(
            ["assessment_id", "module_id"],
            ["assessments.id", "assessments.module_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["topic_id", "module_id"], ["topics.id", "topics.module_id"], ondelete="CASCADE"
        ),
        Index("ix_assessment_topics_topic", "topic_id"),
    )

    assessment_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    topic_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    module_id: Mapped[uuid.UUID]


class Task(TimestampedBase):
    __tablename__ = "tasks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["module_id", "user_id"], ["modules.id", "modules.user_id"], ondelete="CASCADE"
        ),
        # Deleting an assessment unlinks its tasks but keeps module_id (PG 15+ column list).
        ForeignKeyConstraint(
            ["assessment_id", "module_id"],
            ["assessments.id", "assessments.module_id"],
            ondelete="SET NULL (assessment_id)",
        ),
        UniqueConstraint("id", "user_id", name="uq_tasks_id_user"),
        CheckConstraint(_in("status", TASK_STATUSES), name="ck_tasks_status"),
        Index("ix_tasks_module", "module_id"),
        Index("ix_tasks_assessment", "assessment_id"),
    )

    user_id: Mapped[uuid.UUID]
    module_id: Mapped[uuid.UUID]
    assessment_id: Mapped[uuid.UUID | None]
    title: Mapped[str] = mapped_column(String(200))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="todo", server_default="todo")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
