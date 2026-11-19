"""Schemas for the tutor: conversations, messages, and the events of a streamed answer."""

import re
import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.schemas.academics import _Input
from app.services.tutor.prompts import MessageMode, TutorMode

MessageStatus = Literal["complete", "truncated", "failed", "stopped"]


class ConversationCreate(_Input):
    """Both optional. A study session must be in the module; without a topic, the session's
    topic (if any) is the one retrieval boosts."""

    study_session_id: uuid.UUID | None = None
    topic_id: uuid.UUID | None = None


class MessageCreate(_Input):
    question: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
    ]
    mode: TutorMode = "answer"


# --- "Quiz me" (validated before it's stored in messages.quiz) ---

QUIZ_OPTIONS = 4
Option = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
_LABEL = re.compile(r"[\[【]?\s*[sS](\d+)\s*[\]】]?")


class QuizQuestion(BaseModel):
    """One multiple-choice question. Extra keys from the model are ignored."""

    model_config = ConfigDict(extra="ignore")

    prompt: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    options: list[Option] = Field(min_length=QUIZ_OPTIONS, max_length=QUIZ_OPTIONS)
    # The index of the correct option, 0 to 3.
    correct: int = Field(ge=0, le=QUIZ_OPTIONS - 1)
    # One line on why it's right, citing its source like [S1].
    explanation: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)
    ]
    # The source labels it's based on, like ["S1", "S3"]. Code drops a question whose
    # labels aren't all among the answer's sources.
    sources: list[str] = Field(min_length=1, max_length=8)

    @field_validator("sources", mode="before")
    @classmethod
    def _plain_labels(cls, value: object) -> object:
        """ "[S1]", "【S1】" and "s1" all mean "S1"; anything else is kept, and won't match."""
        if not isinstance(value, list):
            return value
        labels: list[object] = []
        for item in value:
            match = _LABEL.fullmatch(item.strip()) if isinstance(item, str) else None
            labels.append(f"S{int(match.group(1))}" if match else item)
        return labels


class Quiz(BaseModel):
    """What the model is asked for (3 questions); up to 6 are accepted, then filtered."""

    model_config = ConfigDict(extra="ignore")

    questions: list[QuizQuestion] = Field(min_length=1, max_length=6)


class QuizAnswersIn(_Input):
    """The student's pick for each question, in order (null for one not answered yet)."""

    answers: list[Annotated[int, Field(ge=0, le=QUIZ_OPTIONS - 1)] | None] = Field(max_length=6)


class MessageSourceOut(BaseModel):
    """A source the answer was given. ``material_id`` is null once the material is deleted."""

    model_config = ConfigDict(from_attributes=True)

    label: str
    rank: int
    material_id: uuid.UUID | None
    material_title: str
    page_number: int
    page_title: str | None
    cited: bool


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: Literal["user", "assistant"]
    mode: MessageMode
    text: str
    status: MessageStatus
    # "provider/model" that answered (answers only).
    model: str | None
    # Measured, in milliseconds, from receiving the question (answers only).
    first_token_ms: int | None
    total_ms: int | None
    # Labels the answer cited that weren't among its sources.
    unknown_citations: list[str]
    created_at: datetime
    sources: list[MessageSourceOut]
    # A "Quiz me" answer's questions, and the student's picks (null until answered).
    quiz: Quiz | None = None
    quiz_answers: list[int | None] | None = None


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    module_id: uuid.UUID
    study_session_id: uuid.UUID | None
    topic_id: uuid.UUID | None
    created_at: datetime
    # Oldest first.
    messages: list[MessageOut]


# --- the events of POST /conversations/{id}/messages (text/event-stream) ---


class SourceOut(BaseModel):
    """A source as the student sees it before the answer: enough to link to the page."""

    model_config = ConfigDict(from_attributes=True)

    label: str
    material_id: uuid.UUID
    material_title: str
    page_number: int
    page_title: str | None


class SourcesEvent(BaseModel):
    """First: the sources the answer is given (may be empty)."""

    sources: list[SourceOut]


class DeltaEvent(BaseModel):
    """A piece of the answer, in order."""

    text: str


class DoneEvent(BaseModel):
    """Last, when an answer was given (``truncated`` if it hit the output limit)."""

    message_id: uuid.UUID
    status: Literal["complete", "truncated"]
    model: str
    first_token_ms: int
    total_ms: int
    # Valid labels the answer cited, in the sources' order.
    cited: list[str]
    # Labels it cited that weren't among its sources (left out of ``cited``).
    unknown_citations: list[str]


class ErrorEvent(BaseModel):
    """Last, when no full answer was given. Any text already streamed is kept as a
    ``failed`` message."""

    message_id: uuid.UUID
    message: str
    # When to try again (AI busy or out of quota); null when retrying won't help.
    retry_at: datetime | None = Field(default=None)
