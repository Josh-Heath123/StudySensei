"""Stored plans: versions and their blocks (Phase 4, decision 0021).

A **version** is one run of the planner that changed something: its number (1, 2, … per
user), why it exists (``trigger`` and a code-written ``summary``) and the feasibility report
exactly as ``GET /plan/preview`` returns it. A re-plan that changes nothing writes no version;
it refreshes ``checked_at`` and the report instead.

A **block** belongs to one version. Its texts are as generated for that version, and its
status moves from ``planned`` to ``done`` (a linked session ended), ``skipped`` (the student
said so) or ``missed`` (it ended with nothing linked). ``fixed`` blocks were carried from the
previous version (the next 24 h). Old versions and their blocks are kept, never pruned.

Isolation follows ``academics.py``: UNIQUE (id, user_id), and composite FKs on
``(…, user_id)``, so a block can't point at another user's version, module, assessment or
topic. Deleting a module, assessment or topic deletes its blocks.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.academics import _in
from app.models.base import TimestampedBase

TRIGGERS = (
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
BLOCK_KINDS = ("study", "review")
BLOCK_REASONS = ("final_review", "spacing", "no_estimate", "low_confidence", "urgency", "workload")
BLOCK_METHODS = ("mixed_review", "first_pass", "active_recall", "practice")
BLOCK_STATUSES = ("planned", "done", "skipped", "missed")


class PlanVersion(TimestampedBase):
    __tablename__ = "plan_versions"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_plan_versions_id_user"),
        UniqueConstraint("user_id", "number", name="uq_plan_versions_user_number"),
        CheckConstraint("number >= 1", name="ck_plan_versions_number"),
        CheckConstraint(_in("trigger", TRIGGERS), name="ck_plan_versions_trigger"),
        CheckConstraint("days BETWEEN 1 AND 62", name="ck_plan_versions_days"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    trigger: Mapped[str] = mapped_column(String(20))
    summary: Mapped[str] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # When a re-plan last confirmed this version (equals generated_at until then).
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    days: Mapped[int] = mapped_column(SmallInteger)
    # The feasibility report, as GET /plan/preview returns it.
    report: Mapped[dict[str, Any]] = mapped_column(JSONB)


class PlanBlock(TimestampedBase):
    __tablename__ = "plan_blocks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["version_id", "user_id"],
            ["plan_versions.id", "plan_versions.user_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["module_id", "user_id"], ["modules.id", "modules.user_id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["assessment_id", "user_id"],
            ["assessments.id", "assessments.user_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["topic_id", "user_id"], ["topics.id", "topics.user_id"], ondelete="CASCADE"
        ),
        UniqueConstraint("id", "user_id", name="uq_plan_blocks_id_user"),
        CheckConstraint("end_at > start_at", name="ck_plan_blocks_times"),
        CheckConstraint(_in("kind", BLOCK_KINDS), name="ck_plan_blocks_kind"),
        CheckConstraint(_in("reason", BLOCK_REASONS), name="ck_plan_blocks_reason"),
        CheckConstraint(_in("method", BLOCK_METHODS), name="ck_plan_blocks_method"),
        CheckConstraint(_in("status", BLOCK_STATUSES), name="ck_plan_blocks_status"),
        # A review covers the assessment's topics; a study block has one.
        CheckConstraint("(kind = 'review') = (topic_id IS NULL)", name="ck_plan_blocks_topic"),
        Index("ix_plan_blocks_user_start", "user_id", "start_at"),
        Index("ix_plan_blocks_version", "version_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    version_id: Mapped[uuid.UUID]
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    module_id: Mapped[uuid.UUID]
    assessment_id: Mapped[uuid.UUID]
    topic_id: Mapped[uuid.UUID | None]
    kind: Mapped[str] = mapped_column(String(10))
    reason: Mapped[str] = mapped_column(String(20))
    method: Mapped[str] = mapped_column(String(20))
    reason_text: Mapped[str] = mapped_column(Text)
    method_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="planned", server_default="planned")
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Carried from the previous version (it started within the next 24 h, or is pinned).
    fixed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # The student moved it (decision 0022): re-plans keep it at its time while it's valid.
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
