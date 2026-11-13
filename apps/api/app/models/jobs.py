"""Background jobs, queued in Postgres (decision 0004).

The worker claims the next due job with ``FOR UPDATE SKIP LOCKED``, so several
workers can run without taking the same job. Jobs carry ``user_id`` so every
handler can scope its queries by it.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.academics import _in
from app.models.base import TimestampedBase

JOB_STATUSES = ("queued", "running", "succeeded", "failed")


class Job(TimestampedBase):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(_in("status", JOB_STATUSES), name="ck_jobs_status"),
        CheckConstraint("attempts >= 0 AND max_attempts >= 1", name="ck_jobs_attempts"),
        CheckConstraint(
            "(status = 'running') = (locked_at IS NOT NULL)", name="ck_jobs_running_locked"
        ),
        # The worker's "next due job" query.
        Index("ix_jobs_due", "run_after", postgresql_where=text("status = 'queued'")),
        Index("ix_jobs_user_kind", "user_id", "kind"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued", server_default="queued")
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(SmallInteger, default=3, server_default="3")
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
