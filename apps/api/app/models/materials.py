"""Course materials: uploaded files belonging to a module.

The bytes live in Storage under ``{user_id}/{sha256}``; this table holds what
the file is and how far processing has got. Isolation follows
``app/models/academics.py`` (composite FK to ``modules(id, user_id)``).

``allow_ai`` is the student's switch for AI processing. AI jobs must check it;
the student turns it off for their own submissions.
"""

import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.academics import _in
from app.models.base import TimestampedBase

MATERIAL_KINDS = (
    "slides",
    "notes",
    "study_guide",
    "tutorial",
    "past_paper",
    "test",
    "assignment",
    "outline",
    "other",
)
MATERIAL_STATUSES = ("uploaded", "processing", "ready", "failed")


class Material(TimestampedBase):
    __tablename__ = "materials"
    __table_args__ = (
        ForeignKeyConstraint(
            ["module_id", "user_id"], ["modules.id", "modules.user_id"], ondelete="CASCADE"
        ),
        UniqueConstraint("id", "user_id", name="uq_materials_id_user"),
        UniqueConstraint("id", "module_id", name="uq_materials_id_module"),
        # The same file twice in one module is a duplicate (409).
        UniqueConstraint("module_id", "sha256", name="uq_materials_module_sha256"),
        CheckConstraint(_in("kind", MATERIAL_KINDS), name="ck_materials_kind"),
        CheckConstraint(_in("status", MATERIAL_STATUSES), name="ck_materials_status"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_materials_sha256"),
        CheckConstraint("size_bytes > 0", name="ck_materials_size"),
        CheckConstraint("page_count IS NULL OR page_count >= 0", name="ck_materials_pages"),
        # Blob refcounts look materials up by (user, hash).
        Index("ix_materials_user_sha256", "user_id", "sha256"),
        Index("ix_materials_module_created", "module_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID]
    module_id: Mapped[uuid.UUID]
    kind: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    page_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="uploaded", server_default="uploaded")
    error: Mapped[str | None] = mapped_column(Text)
    allow_ai: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
