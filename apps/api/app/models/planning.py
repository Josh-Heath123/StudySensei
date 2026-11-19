"""When the student can study: weekly windows and per-date exceptions (Phase 4).

Times are minutes after local midnight in the user's timezone (``users.timezone``), with
``0 <= start_minute < end_minute <= 1440``: a window never crosses midnight (split it).
``services/planning/availability.py`` turns them into UTC intervals.

Overlaps are refused by Postgres, not just by the API: an exclusion constraint (btree_gist)
on ``int4range(start_minute, end_minute)`` per user and weekday. An exception's windows are
a small JSON list, validated by the schema (sorted, in range, not overlapping).
"""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    literal_column,
)
from sqlalchemy.dialects.postgresql import JSONB, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedBase

WINDOW_CHECK = "start_minute >= 0 AND start_minute < end_minute AND end_minute <= 1440"


class AvailabilityRule(TimestampedBase):
    """A weekly window: every ``weekday`` (0 is Monday) from start to end, local time."""

    __tablename__ = "availability_rules"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_availability_rules_id_user"),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_availability_rules_weekday"),
        CheckConstraint(WINDOW_CHECK, name="ck_availability_rules_window"),
        ExcludeConstraint(
            ("user_id", "="),
            ("weekday", "="),
            (literal_column("int4range(start_minute, end_minute)"), "&&"),
            name="ex_availability_rules_overlap",
            using="gist",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    weekday: Mapped[int] = mapped_column(SmallInteger)
    start_minute: Mapped[int] = mapped_column(Integer)
    end_minute: Mapped[int] = mapped_column(Integer)


class AvailabilityException(TimestampedBase):
    """One date that doesn't follow the rules: unavailable all day, or its own windows."""

    __tablename__ = "availability_exceptions"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_availability_exceptions_id_user"),
        UniqueConstraint("user_id", "date", name="uq_availability_exceptions_date"),
        # Unavailable means no windows; otherwise at least one.
        CheckConstraint(
            "unavailable = (jsonb_array_length(windows) = 0)",
            name="ck_availability_exceptions_windows",
        ),
        Index("ix_availability_exceptions_user_date", "user_id", "date"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date)
    unavailable: Mapped[bool] = mapped_column(Boolean)
    # [{"start": 540, "end": 720}, …] in minutes, sorted and not overlapping.
    windows: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    note: Mapped[str | None] = mapped_column(String(200))
