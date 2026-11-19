"""Tutor conversations, their messages, and the sources each answer was given (Phase 3).

Isolation follows ``app/models/academics.py``: every table has ``user_id`` and composite
FKs that include it (or ``module_id``), so Postgres rejects a cross-user link:
- a conversation's study session and topic must be in its module;
- a message belongs to a conversation of the same user, a source to a message of the
  same user, and a source's material to the same user.

Only what the student asked, the answer and where it came from are stored. The prompt
itself is rebuilt from these, never stored.
"""

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    text as sql,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.academics import _in
from app.models.base import TimestampedBase

MESSAGE_ROLES = ("user", "assistant")
TUTOR_MODES = ("answer", "explain_differently", "example", "quiz")
MESSAGE_STATUSES = ("complete", "truncated", "failed", "stopped")


class Conversation(TimestampedBase):
    __tablename__ = "conversations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["module_id", "user_id"], ["modules.id", "modules.user_id"], ondelete="CASCADE"
        ),
        # Deleting the session or the topic keeps the conversation, without it.
        ForeignKeyConstraint(
            ["study_session_id", "module_id"],
            ["study_sessions.id", "study_sessions.module_id"],
            ondelete="SET NULL (study_session_id)",
        ),
        ForeignKeyConstraint(
            ["topic_id", "module_id"],
            ["topics.id", "topics.module_id"],
            ondelete="SET NULL (topic_id)",
        ),
        UniqueConstraint("id", "user_id", name="uq_conversations_id_user"),
        Index("ix_conversations_user_module", "user_id", "module_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID]
    module_id: Mapped[uuid.UUID]
    study_session_id: Mapped[uuid.UUID | None]
    # The topic retrieval boosts (ARCHITECTURE "Search": tutor retrieval).
    topic_id: Mapped[uuid.UUID | None]


class Message(TimestampedBase):
    __tablename__ = "messages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["conversation_id", "user_id"],
            ["conversations.id", "conversations.user_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("id", "user_id", name="uq_messages_id_user"),
        # Order within the conversation (created_at is the transaction's time, so it ties).
        UniqueConstraint("conversation_id", "position", name="uq_messages_position"),
        CheckConstraint(_in("role", MESSAGE_ROLES), name="ck_messages_role"),
        CheckConstraint(_in("mode", TUTOR_MODES), name="ck_messages_mode"),
        CheckConstraint(_in("status", MESSAGE_STATUSES), name="ck_messages_status"),
        CheckConstraint("position >= 0", name="ck_messages_position"),
        # Only answers have a model and timings.
        CheckConstraint(
            "role = 'assistant' OR (model IS NULL AND first_token_ms IS NULL AND total_ms IS NULL)",
            name="ck_messages_user_has_no_model",
        ),
        CheckConstraint(
            "(first_token_ms IS NULL OR first_token_ms >= 0) "
            "AND (total_ms IS NULL OR total_ms >= 0)",
            name="ck_messages_timings",
        ),
    )

    user_id: Mapped[uuid.UUID]
    conversation_id: Mapped[uuid.UUID]
    position: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(10))
    # What the student asked for; the answer carries the same mode.
    mode: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10))
    # "provider/model" that answered; None for the student's messages and for an answer
    # no model could give.
    model: Mapped[str | None] = mapped_column(String(120))
    # From receiving the question to the first answer token, and to the end (measured).
    first_token_ms: Mapped[int | None] = mapped_column(Integer)
    total_ms: Mapped[int | None] = mapped_column(Integer)
    # Labels the answer cited that weren't among its sources (e.g. "S9"). The text keeps
    # them; they're left out of the citations.
    unknown_citations: Mapped[list[str]] = mapped_column(
        ARRAY(String(10)), default=list, server_default=sql("'{}'")
    )
    # The sources an answer was given, S1 first (none for the student's messages).
    sources: Mapped[list["MessageSource"]] = relationship(
        order_by="MessageSource.rank", cascade="all, delete-orphan", lazy="raise"
    )


class MessageSource(TimestampedBase):
    """One source an answer was given, [S1] to [S8], and whether the answer cited it."""

    __tablename__ = "message_sources"
    __table_args__ = (
        ForeignKeyConstraint(
            ["message_id", "user_id"],
            ["messages.id", "messages.user_id"],
            ondelete="CASCADE",
        ),
        # Deleting the material keeps the row (and its titles), so old answers still read.
        ForeignKeyConstraint(
            ["material_id", "user_id"],
            ["materials.id", "materials.user_id"],
            ondelete="SET NULL (material_id)",
        ),
        UniqueConstraint("message_id", "label", name="uq_message_sources_label"),
        UniqueConstraint("message_id", "rank", name="uq_message_sources_rank"),
        CheckConstraint("rank BETWEEN 1 AND 8", name="ck_message_sources_rank"),
        CheckConstraint("label = 'S' || rank", name="ck_message_sources_label"),
        CheckConstraint("page_number >= 1", name="ck_message_sources_page"),
    )

    user_id: Mapped[uuid.UUID]
    message_id: Mapped[uuid.UUID]
    label: Mapped[str] = mapped_column(String(3))
    rank: Mapped[int] = mapped_column(SmallInteger)
    material_id: Mapped[uuid.UUID | None]
    # Copied when the answer was given, so the citation still reads if the material goes.
    material_title: Mapped[str] = mapped_column(String(200))
    page_number: Mapped[int] = mapped_column(Integer)
    page_title: Mapped[str | None] = mapped_column(String(500))
    cited: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sql("false"))
