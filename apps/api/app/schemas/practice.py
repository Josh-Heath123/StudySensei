"""Schemas for practice items (Phase 5, ADR 0025): what the AI must return, and the API's.

The AI's reply is validated against ``GeneratedPractice`` before anything is stored; code
then filters it (``services/practice/filter.py``).
"""

import uuid
from datetime import datetime
from typing import Annotated, ClassVar, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.models.practice import ANSWER_MAX, KEY_POINTS_MAX, PROMPT_MAX, REVIEW_ANSWER_MAX
from app.schemas.academics import _Input, _Update
from app.schemas.labels import plain_labels

ItemKind = Literal["flashcard", "short_answer"]
ItemOrigin = Literal["ai", "user"]
ItemStatus = Literal["active", "suspended", "rejected"]
RejectReason = Literal["wrong", "unclear", "not_in_source", "duplicate", "other"]
GenerationStatus = Literal["queued", "running", "succeeded", "failed"]
DropReason = Literal[
    "not_grounded", "duplicate", "too_short", "answer_repeats_prompt", "missing_key_points"
]

Prompt = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=PROMPT_MAX)
]
Answer = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=ANSWER_MAX)
]
KeyPoint = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]

GENERATE_MIN, GENERATE_MAX, GENERATE_DEFAULT = 4, 12, 8


# --- What the AI returns ----------------------------------------------------------------


class GeneratedItem(BaseModel):
    """One item as the model writes it. Extra keys are ignored. A short answer with no key
    points passes the schema (the filter drops it, counted), so one slip doesn't fail the
    whole batch."""

    model_config = ConfigDict(extra="ignore")

    kind: ItemKind
    prompt: Prompt
    answer: Answer
    key_points: list[KeyPoint] | None = Field(default=None, max_length=KEY_POINTS_MAX)
    # The source labels it rests on, like ["S1", "S3"].
    sources: list[str] = Field(min_length=1, max_length=8)

    _plain_labels = field_validator("sources", mode="before")(plain_labels)


class GeneratedPractice(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[GeneratedItem] = Field(min_length=1, max_length=GENERATE_MAX)


# --- API ------------------------------------------------------------------------------


class GenerateIn(_Input):
    count: int = Field(default=GENERATE_DEFAULT, ge=GENERATE_MIN, le=GENERATE_MAX)


class GenerationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    module_id: uuid.UUID
    topic_id: uuid.UUID
    status: GenerationStatus
    requested: int
    produced: int
    # Items the filter dropped, by reason (counts).
    dropped: dict[str, int]
    provider: str | None
    model: str | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None


def _key_points_fit_kind(kind: str | None, key_points: list[str] | None) -> None:
    if kind == "flashcard" and key_points:
        raise ValueError("A flashcard has no key points")
    if kind == "short_answer" and not key_points:
        raise ValueError("A short-answer question needs 1 to 5 key points")


class ItemCreate(_Input):
    """The student's own card or question."""

    module_id: uuid.UUID
    topic_id: uuid.UUID | None = None
    kind: ItemKind
    prompt: Prompt
    answer: Answer
    key_points: list[KeyPoint] | None = Field(default=None, max_length=KEY_POINTS_MAX)

    @model_validator(mode="after")
    def _check_key_points(self) -> Self:
        _key_points_fit_kind(self.kind, self.key_points)
        return self


class ItemUpdate(_Update):
    """Text edits make an AI item the student's (decision 0009). ``reject_reason`` is
    required when, and only when, the status becomes rejected."""

    nullable: ClassVar[frozenset[str]] = frozenset({"topic_id", "reject_reason"})

    prompt: Prompt | None = None
    answer: Answer | None = None
    key_points: list[KeyPoint] | None = Field(default=None, max_length=KEY_POINTS_MAX)
    topic_id: uuid.UUID | None = None
    status: ItemStatus | None = None
    reject_reason: RejectReason | None = None

    @model_validator(mode="after")
    def _check_reason(self) -> Self:
        if self.status == "rejected" and self.reject_reason is None:
            raise ValueError("Say why the item is rejected (reject_reason)")
        if self.reject_reason is not None and self.status != "rejected":
            raise ValueError("reject_reason goes with status rejected")
        return self


class ItemSourceOut(BaseModel):
    label: str
    material_id: uuid.UUID
    material_title: str
    page_number: int


class ItemOut(BaseModel):
    id: uuid.UUID
    module_id: uuid.UUID
    topic_id: uuid.UUID | None
    kind: ItemKind
    prompt: str
    answer: str
    key_points: list[str] | None
    origin: ItemOrigin
    status: ItemStatus
    reject_reason: RejectReason | None
    provider: str | None
    model: str | None
    generation_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    sources: list[ItemSourceOut]
    # An AI item whose cited passages were all deleted (with their material).
    sources_missing: bool


class ItemPage(BaseModel):
    items: list[ItemOut]
    total: int


class ReviewIn(_Input):
    grade: int = Field(ge=1, le=4, description="1 again, 2 hard, 3 good, 4 easy")
    duration_ms: int | None = Field(default=None, ge=0, le=86_400_000)
    answer_text: Annotated[str, StringConstraints(max_length=REVIEW_ANSWER_MAX)] | None = None


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    item_id: uuid.UUID
    reviewed_at: datetime
    grade: int
    marked_by: Literal["self", "ai"]
    duration_ms: int | None
    answer_text: str | None
