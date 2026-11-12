"""Input schemas for the academic structure.

Create schemas carry required fields; Update schemas make everything optional and
are applied with ``model_dump(exclude_unset=True)`` so omitted fields stay as they are.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Colour = Annotated[str, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$")]
Semester = Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)]
Weight = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]

AssessmentKind = Literal["exam", "test", "assignment", "quiz", "project", "other"]
AssessmentStatus = Literal["upcoming", "completed", "cancelled"]
TaskStatus = Literal["todo", "in_progress", "done"]


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModuleCreate(_Input):
    code: Code
    name: Name
    colour: Colour = "#007AFF"
    semester: Semester | None = None


class ModuleUpdate(_Input):
    code: Code | None = None
    name: Name | None = None
    colour: Colour | None = None
    semester: Semester | None = None


class TopicCreate(_Input):
    name: Name
    description: str | None = None
    parent_id: uuid.UUID | None = None
    position: int = Field(default=0, ge=0)


class TopicUpdate(_Input):
    name: Name | None = None
    description: str | None = None


class AssessmentCreate(_Input):
    title: Name
    kind: AssessmentKind
    due_at: datetime | None = None
    weight: Weight | None = None
    status: AssessmentStatus = "upcoming"
    notes: str | None = None


class AssessmentUpdate(_Input):
    title: Name | None = None
    kind: AssessmentKind | None = None
    due_at: datetime | None = None
    weight: Weight | None = None
    status: AssessmentStatus | None = None
    notes: str | None = None


class TaskCreate(_Input):
    title: Name
    assessment_id: uuid.UUID | None = None
    due_at: datetime | None = None
    status: TaskStatus = "todo"
    notes: str | None = None


class TaskUpdate(_Input):
    title: Name | None = None
    assessment_id: uuid.UUID | None = None
    due_at: datetime | None = None
    status: TaskStatus | None = None
    notes: str | None = None
