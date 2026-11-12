"""Input schemas for the academic structure.

Create schemas carry required fields. Update schemas make every field optional and
are applied with ``model_dump(exclude_unset=True)``, so omitted fields stay as they are.
An explicit null is only accepted for fields listed in ``nullable`` (columns that can
really be cleared); for anything else it's a 422, not a NOT NULL error from Postgres.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, ClassVar, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

# Module codes are stored upper-case so "cos330" and "COS330" are the same module.
Code = Annotated[
    str, StringConstraints(strip_whitespace=True, to_upper=True, min_length=1, max_length=20)
]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Colour = Annotated[str, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$")]
Semester = Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)]
Weight = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]

AssessmentKind = Literal["exam", "test", "assignment", "quiz", "project", "other"]
AssessmentStatus = Literal["upcoming", "completed", "cancelled"]
TaskStatus = Literal["todo", "in_progress", "done"]


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Update(_Input):
    """Base for PATCH bodies: null is only allowed for the fields in ``nullable``."""

    nullable: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def _reject_null_for_required(self) -> Self:
        for name in self.model_fields_set:
            if getattr(self, name) is None and name not in self.nullable:
                raise ValueError(f"{name} cannot be null")
        return self


class ModuleCreate(_Input):
    code: Code
    name: Name
    colour: Colour = "#007AFF"
    semester: Semester | None = None


class ModuleUpdate(_Update):
    nullable = frozenset({"semester"})

    code: Code | None = None
    name: Name | None = None
    colour: Colour | None = None
    semester: Semester | None = None


class TopicCreate(_Input):
    name: Name
    description: str | None = None
    parent_id: uuid.UUID | None = None
    # Index among its siblings; omitted means "after the last one".
    position: int | None = Field(default=None, ge=0)


class TopicUpdate(_Update):
    nullable = frozenset({"description"})

    name: Name | None = None
    description: str | None = None


class AssessmentCreate(_Input):
    title: Name
    kind: AssessmentKind
    # Must carry a timezone (e.g. "...Z" or "+02:00"); a bare local time is ambiguous.
    due_at: AwareDatetime | None = None
    weight: Weight | None = None
    status: AssessmentStatus = "upcoming"
    notes: str | None = None
    # Topics it covers; all must be in the assessment's module.
    topic_ids: list[uuid.UUID] = Field(default_factory=list)


class AssessmentUpdate(_Update):
    nullable = frozenset({"due_at", "weight", "notes"})

    title: Name | None = None
    kind: AssessmentKind | None = None
    due_at: AwareDatetime | None = None
    weight: Weight | None = None
    status: AssessmentStatus | None = None
    notes: str | None = None
    # Omitted: unchanged. []: covers no topics. Otherwise replaces the whole set.
    topic_ids: list[uuid.UUID] | None = None


class TaskCreate(_Input):
    title: Name
    assessment_id: uuid.UUID | None = None
    due_at: AwareDatetime | None = None
    status: TaskStatus = "todo"
    notes: str | None = None


class TaskUpdate(_Update):
    nullable = frozenset({"assessment_id", "due_at", "notes"})

    title: Name | None = None
    assessment_id: uuid.UUID | None = None
    due_at: AwareDatetime | None = None
    status: TaskStatus | None = None
    notes: str | None = None


class TopicMove(_Input):
    """Move a topic under ``parent_id`` (null = top level) at index ``position``."""

    parent_id: uuid.UUID | None
    position: int = Field(ge=0)


# --- Responses -----------------------------------------------------------------------


class ModuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    colour: str
    semester: str | None
    created_at: datetime
    updated_at: datetime


class TopicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    module_id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    description: str | None
    position: int
    source: Literal["user", "ai"]


class TopicNodeOut(TopicOut):
    """A topic with its subtopics, for rendering the tree."""

    children: list["TopicNodeOut"]
