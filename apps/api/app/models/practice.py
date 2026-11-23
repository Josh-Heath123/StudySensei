"""Practice items, their sources and reviews, and the AI runs that write them (Phase 5, ADR 0025).

- An **item** is a flashcard (one fact, definition or contrast: ``prompt`` is the front,
  ``answer`` the back) or a short-answer question (``answer`` is the reference answer and
  ``key_points`` the 1 to 5 points a full answer must contain). The AI writes them
  (``origin`` ai, with its ``provider``, ``model`` and ``generation_id``) or the student
  does (``origin`` user). Editing an AI item's text makes it the student's, as with topics
  (decision 0009); where it came from (its provider, model, generation and sources) stays.
- ``prompt_key`` is sha256 of the prompt, lower-cased with whitespace collapsed: a topic
  can't hold the same prompt twice unless one of them was rejected.
- An item's **sources** are the passages it cites (labels S1… as the prompt had them). They
  go with their chunk: deleting a material leaves an AI item with no sources, which the API
  reports as ``sources_missing``.
- A **generation** is one AI run for a topic: what was asked, what was kept and why the rest
  were dropped (counts only).
- A **review** is one answer to an item: a grade from 1 (again) to 4 (easy). Append-only:
  Postgres refuses an UPDATE (``trg_reviews_append_only``); rows go only with their item.

Isolation follows ``academics.py``: UNIQUE (id, user_id), and composite FKs that include
``user_id`` (or ``module_id``), so nothing here can point at another user's rows. Deleting a
module deletes its items and generations; deleting a topic leaves its items with no topic.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.academics import _in
from app.models.base import Base, TimestampedBase

ITEM_KINDS = ("flashcard", "short_answer")
ITEM_ORIGINS = ("ai", "user")
ITEM_STATUSES = ("active", "suspended", "rejected")
REJECT_REASONS = ("wrong", "unclear", "not_in_source", "duplicate", "other")
GENERATION_STATUSES = ("queued", "running", "succeeded", "failed")
REVIEW_MARKERS = ("self", "ai")
MEMORY_STATES = ("learning", "review", "relearning")

PROMPT_MAX = 500
ANSWER_MAX = 1500
KEY_POINTS_MAX = 5
REVIEW_ANSWER_MAX = 2000


class PracticeGeneration(TimestampedBase):
    __tablename__ = "practice_generations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["module_id", "user_id"], ["modules.id", "modules.user_id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["topic_id", "module_id"], ["topics.id", "topics.module_id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        UniqueConstraint("id", "user_id", name="uq_practice_generations_id_user"),
        CheckConstraint(_in("status", GENERATION_STATUSES), name="ck_practice_generations_status"),
        CheckConstraint("requested BETWEEN 1 AND 12", name="ck_practice_generations_requested"),
        CheckConstraint("produced >= 0", name="ck_practice_generations_produced"),
        # One generation at a time per topic: a second request is a 409.
        Index(
            "uq_practice_generations_one_active",
            "topic_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
        Index("ix_practice_generations_topic", "topic_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID]
    module_id: Mapped[uuid.UUID]
    topic_id: Mapped[uuid.UUID]
    status: Mapped[str] = mapped_column(String(10), default="queued", server_default="queued")
    requested: Mapped[int] = mapped_column(SmallInteger)
    produced: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    # Items the filter dropped, by reason: {"not_grounded": 1, "duplicate": 2, ...}.
    dropped: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict, server_default="{}")
    provider: Mapped[str | None] = mapped_column(String(20))
    model: Mapped[str | None] = mapped_column(String(100))
    # Why it failed, in words for the student.
    error: Mapped[str | None] = mapped_column(Text)
    job_id: Mapped[uuid.UUID | None]
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PracticeItem(TimestampedBase):
    __tablename__ = "practice_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["module_id", "user_id"], ["modules.id", "modules.user_id"], ondelete="CASCADE"
        ),
        # Deleting the topic keeps the item, with no topic (PG 15+ column list).
        ForeignKeyConstraint(
            ["topic_id", "module_id"],
            ["topics.id", "topics.module_id"],
            ondelete="SET NULL (topic_id)",
        ),
        ForeignKeyConstraint(
            ["generation_id", "user_id"],
            ["practice_generations.id", "practice_generations.user_id"],
            ondelete="SET NULL (generation_id)",
        ),
        UniqueConstraint("id", "user_id", name="uq_practice_items_id_user"),
        CheckConstraint(_in("kind", ITEM_KINDS), name="ck_practice_items_kind"),
        CheckConstraint(_in("origin", ITEM_ORIGINS), name="ck_practice_items_origin"),
        CheckConstraint(_in("status", ITEM_STATUSES), name="ck_practice_items_status"),
        CheckConstraint(
            f"char_length(prompt) BETWEEN 1 AND {PROMPT_MAX}", name="ck_practice_items_prompt"
        ),
        CheckConstraint(
            f"char_length(answer) BETWEEN 1 AND {ANSWER_MAX}", name="ck_practice_items_answer"
        ),
        # Key points belong to short answers only: 1 to 5 of them.
        CheckConstraint(
            "(kind = 'flashcard' AND key_points IS NULL) OR (kind = 'short_answer' "
            "AND key_points IS NOT NULL AND jsonb_typeof(key_points) = 'array' "
            f"AND jsonb_array_length(key_points) BETWEEN 1 AND {KEY_POINTS_MAX})",
            name="ck_practice_items_key_points",
        ),
        # A reason exactly when rejected.
        CheckConstraint(
            "(status = 'rejected') = (reject_reason IS NOT NULL)",
            name="ck_practice_items_reject_reason",
        ),
        CheckConstraint(
            f"reject_reason IS NULL OR {_in('reject_reason', REJECT_REASONS)}",
            name="ck_practice_items_reject_reasons",
        ),
        # An AI item says which model wrote it; the student's own never claim one.
        CheckConstraint(
            "origin = 'user' OR (provider IS NOT NULL AND model IS NOT NULL)",
            name="ck_practice_items_ai_model",
        ),
        CheckConstraint("char_length(prompt_key) = 64", name="ck_practice_items_prompt_key"),
        Index(
            "uq_practice_items_topic_prompt",
            "user_id",
            "topic_id",
            "prompt_key",
            unique=True,
            postgresql_where=text("status <> 'rejected'"),
        ),
        Index("ix_practice_items_module", "module_id", "created_at"),
        Index("ix_practice_items_topic", "topic_id"),
    )

    user_id: Mapped[uuid.UUID]
    module_id: Mapped[uuid.UUID]
    topic_id: Mapped[uuid.UUID | None]
    kind: Mapped[str] = mapped_column(String(20))
    prompt: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    key_points: Mapped[list[str] | None] = mapped_column(JSONB(none_as_null=True))
    origin: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10), default="active", server_default="active")
    reject_reason: Mapped[str | None] = mapped_column(String(20))
    provider: Mapped[str | None] = mapped_column(String(20))
    model: Mapped[str | None] = mapped_column(String(100))
    generation_id: Mapped[uuid.UUID | None]
    prompt_key: Mapped[str] = mapped_column(String(64))


class PracticeItemSource(Base):
    """A passage an item cites, with the label it had in the prompt."""

    __tablename__ = "practice_item_sources"
    __table_args__ = (
        ForeignKeyConstraint(
            ["item_id", "user_id"],
            ["practice_items.id", "practice_items.user_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["chunk_id", "user_id"], ["chunks.id", "chunks.user_id"], ondelete="CASCADE"
        ),
        CheckConstraint("label ~ '^S[1-9][0-9]*$'", name="ck_practice_item_sources_label"),
        Index("ix_practice_item_sources_chunk", "chunk_id"),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    chunk_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID]
    label: Mapped[str] = mapped_column(String(5))


class Review(TimestampedBase):
    __tablename__ = "reviews"
    __table_args__ = (
        ForeignKeyConstraint(
            ["item_id", "user_id"],
            ["practice_items.id", "practice_items.user_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("grade BETWEEN 1 AND 4", name="ck_reviews_grade"),
        CheckConstraint(_in("marked_by", REVIEW_MARKERS), name="ck_reviews_marked_by"),
        CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="ck_reviews_duration_ms"),
        CheckConstraint(
            f"answer_text IS NULL OR char_length(answer_text) <= {REVIEW_ANSWER_MAX}",
            name="ck_reviews_answer_text",
        ),
        Index("ix_reviews_user_item_at", "user_id", "item_id", "reviewed_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    item_id: Mapped[uuid.UUID]
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # 1 again, 2 hard, 3 good, 4 easy (FSRS's grades; task 2 adds the schedule).
    grade: Mapped[int] = mapped_column(SmallInteger)
    marked_by: Mapped[str] = mapped_column(String(10))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    # What the student typed, if anything. Never sent to the AI in this task.
    answer_text: Mapped[str | None] = mapped_column(Text)
    # FSRS (migration 0026, decision 0026); null on reviews from before it. The item's state
    # before and after (``scheduling.MemoryState.snapshot``; before is null for a new item),
    # the whole days until due, the retention used and the library that computed it.
    state_before: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    state_after: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    scheduled_days: Mapped[int | None] = mapped_column(Integer)
    desired_retention: Mapped[float | None] = mapped_column(Double)
    fsrs_version: Mapped[str | None] = mapped_column(String(20))

    @property
    def after(self) -> dict[str, Any] | None:
        """The state and due this review led to (from ``state_after``), for ``ReviewOut``."""
        if self.state_after is None:
            return None
        return {"state": self.state_after["state"], "due": self.state_after["due"]}


class PracticeItemState(Base):
    """An item's FSRS state after its latest review (decision 0026). No row: a new item."""

    __tablename__ = "practice_item_states"
    __table_args__ = (
        ForeignKeyConstraint(
            ["item_id", "user_id"],
            ["practice_items.id", "practice_items.user_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(_in("state", MEMORY_STATES), name="ck_practice_item_states_state"),
        CheckConstraint("step IS NULL OR step >= 0", name="ck_practice_item_states_step"),
        CheckConstraint("stability > 0", name="ck_practice_item_states_stability"),
        CheckConstraint("difficulty BETWEEN 1 AND 10", name="ck_practice_item_states_difficulty"),
        CheckConstraint("reps >= 1 AND lapses >= 0", name="ck_practice_item_states_counts"),
        CheckConstraint("due > last_review_at", name="ck_practice_item_states_due"),
        Index("ix_practice_item_states_user_due", "user_id", "due"),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID]
    state: Mapped[str] = mapped_column(String(10))
    step: Mapped[int | None] = mapped_column(SmallInteger)
    stability: Mapped[float] = mapped_column(Double)
    difficulty: Mapped[float] = mapped_column(Double)
    due: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_review_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reps: Mapped[int] = mapped_column(Integer)
    lapses: Mapped[int] = mapped_column(Integer)
