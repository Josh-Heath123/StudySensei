"""Schemas for course materials."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, computed_field

from app.schemas.academics import Name, _Update

MaterialKind = Literal[
    "slides",
    "notes",
    "study_guide",
    "tutorial",
    "past_paper",
    "test",
    "assignment",
    "outline",
    "other",
]
MaterialStatus = Literal["uploaded", "processing", "ready", "failed"]


class MaterialUpdate(_Update):
    title: Name | None = None
    kind: MaterialKind | None = None
    allow_ai: bool | None = None


class MaterialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    module_id: uuid.UUID
    kind: MaterialKind
    title: str
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    # Null when the format has no pages (MD, TXT) or it isn't known yet.
    page_count: int | None
    # Pages with (almost) no text layer; a later vision step reads them. Null until extracted.
    scanned_page_count: int | None
    status: MaterialStatus
    # Why processing failed, in words safe to show the student.
    error: str | None
    allow_ai: bool
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def retrying(self) -> bool:
        """A failed attempt is waiting to be retried (`error` says why it failed)."""
        return self.status == "processing" and self.error is not None


class PageSummary(BaseModel):
    """A page in the list (no text): for choosing one to open."""

    model_config = ConfigDict(from_attributes=True)

    page_number: int
    title: str | None
    char_count: int
    is_scanned: bool


class PageOut(PageSummary):
    """One page's extracted text, as stored."""

    text: str
