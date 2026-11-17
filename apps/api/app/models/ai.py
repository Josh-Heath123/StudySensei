"""One row per request the LLM client sends to a provider (decision 0002).

It drives the daily budget and makes every AI call visible. It never holds prompt
or reply text: only who, which model, why, how big, how long and how it went.
"""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.academics import _in
from app.models.base import TimestampedBase

AI_ROLES = ("smart", "bulk", "vision", "long")
AI_OUTCOMES = ("ok", "rate_limited", "error", "invalid_json", "timeout", "truncated")


class AIUsage(TimestampedBase):
    __tablename__ = "ai_usage"
    __table_args__ = (
        CheckConstraint(_in("role", AI_ROLES), name="ck_ai_usage_role"),
        CheckConstraint(_in("outcome", AI_OUTCOMES), name="ck_ai_usage_outcome"),
        CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND latency_ms >= 0",
            name="ck_ai_usage_counts",
        ),
        # The budget counts a user's requests to one model since its quota reset.
        Index("ix_ai_usage_budget", "user_id", "provider", "model", "created_at"),
        Index("ix_ai_usage_job", "job_id", postgresql_where=text("job_id IS NOT NULL")),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(10))
    # What the call was for, e.g. "topic_extraction" or "ping".
    purpose: Mapped[str] = mapped_column(String(50))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    latency_ms: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(20))
    # The job that made the call, so a job can count its calls across retries (ADR 0007).
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL", name="fk_ai_usage_job")
    )
    # Why it failed, for diagnosis: the HTTP status and the provider's error message, or a
    # summary of what didn't validate. Never prompt or reply text.
    detail: Mapped[str | None] = mapped_column(String(300))
