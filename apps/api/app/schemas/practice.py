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


class ItemPageOut(BaseModel):
    """A page an item cites, once however many of its passages are cited."""

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
    # The distinct pages of its sources, in label order (two passages of p7 are one p7).
    pages: list[ItemPageOut]
    # An AI item whose cited passages were all deleted (with their material).
    sources_missing: bool
    # FSRS (decision 0026): where the item stands now.
    memory: "MemoryOut"


class ItemPage(BaseModel):
    items: list[ItemOut]
    total: int


# --- AI marking of a short answer (ADR 0029) ---------------------------------------------

Verdict = Literal["correct", "partly", "incorrect"]
FEEDBACK_MAX = 300
# A share of key points covered from which the answer is "partly" right (below it: incorrect).
PARTLY_FROM = 0.5
StudentAnswer = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=REVIEW_ANSWER_MAX)
]
Feedback = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=FEEDBACK_MAX)
]


def verdict_for(covered: int, total: int) -> tuple[Verdict, Literal[1, 2, 3]]:
    """The verdict and the grade it suggests, from the key points covered. Code decides, never
    the model: all covered is correct (Good, 3); at least half is partly (Hard, 2); fewer is
    incorrect (Again, 1). Nothing suggests Easy."""
    if total < 1 or not 0 <= covered <= total:
        raise ValueError("covered must be between 0 and the number of key points")
    if covered == total:
        return "correct", 3
    if covered / total >= PARTLY_FROM:
        return "partly", 2
    return "incorrect", 1


class KeyPointVerdict(BaseModel):
    """The model's judgement on one numbered key point."""

    model_config = ConfigDict(extra="ignore")

    index: int = Field(ge=1, le=KEY_POINTS_MAX)
    covered: bool


class MarkingReply(BaseModel):
    """What the AI must return for a marking: one verdict per key point and a short note.
    ``marking_reply(n)`` adds the check that there's exactly one per key point 1..n."""

    model_config = ConfigDict(extra="ignore")

    key_points: list[KeyPointVerdict] = Field(min_length=1, max_length=KEY_POINTS_MAX)
    feedback: Feedback

    expected: ClassVar[int] = 0

    @model_validator(mode="after")
    def _one_per_key_point(self) -> Self:
        if self.expected:
            found = sorted(k.index for k in self.key_points)
            if found != list(range(1, self.expected + 1)):
                raise ValueError(
                    f"key_points must have exactly one entry for each index 1 to {self.expected}"
                )
        return self


def marking_reply(count: int) -> type[MarkingReply]:
    """The reply schema for an item with ``count`` key points."""
    if not 1 <= count <= KEY_POINTS_MAX:
        raise ValueError("A short answer has 1 to 5 key points")
    return type(f"MarkingReply{count}", (MarkingReply,), {"expected": count})


class MarkIn(_Input):
    answer_text: StudentAnswer


class KeyPointCoverage(BaseModel):
    index: int = Field(ge=1, le=KEY_POINTS_MAX)
    key_point: KeyPoint
    covered: bool


class AIMarking(BaseModel):
    """A marking (``POST /practice/items/{id}/mark``), and the same object sent back with the
    review it led to. The verdict and the suggested grade must be what code derives from the
    coverage, so a client can't record one the AI didn't give."""

    coverage: list[KeyPointCoverage] = Field(min_length=1, max_length=KEY_POINTS_MAX)
    verdict: Verdict
    suggested_grade: Literal[1, 2, 3]
    feedback: Feedback
    # "provider/model" that judged it.
    model: Annotated[str, StringConstraints(min_length=1, max_length=100)]

    @model_validator(mode="after")
    def _derived_by_code(self) -> Self:
        if [c.index for c in self.coverage] != list(range(1, len(self.coverage) + 1)):
            raise ValueError("coverage must list key points 1 to n in order")
        covered = sum(1 for c in self.coverage if c.covered)
        if (self.verdict, self.suggested_grade) != verdict_for(covered, len(self.coverage)):
            raise ValueError("verdict and suggested_grade must follow from the coverage")
        return self


class ReviewIn(_Input):
    grade: int = Field(ge=1, le=4, description="1 again, 2 hard, 3 good, 4 easy")
    duration_ms: int | None = Field(default=None, ge=0, le=86_400_000)
    answer_text: Annotated[str, StringConstraints(max_length=REVIEW_ANSWER_MAX)] | None = None
    # "ai" only when the student pressed the grade the AI suggested; the student always
    # submits the grade.
    marked_by: Literal["self", "ai"] = "self"
    # The marking the student saw, if they asked for one (kept even when they chose another
    # grade, as "self").
    ai_marking: AIMarking | None = None

    @model_validator(mode="after")
    def _ai_needs_its_marking(self) -> Self:
        if self.marked_by == "ai":
            if self.ai_marking is None:
                raise ValueError('marked_by "ai" needs the ai_marking it came from')
            if self.ai_marking.suggested_grade != self.grade:
                raise ValueError('marked_by "ai" is only for the grade the AI suggested')
        return self


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    item_id: uuid.UUID
    reviewed_at: datetime
    grade: int
    marked_by: Literal["self", "ai"]
    duration_ms: int | None
    answer_text: str | None
    # Null on reviews from before scheduling (task 1).
    scheduled_days: int | None
    desired_retention: float | None
    fsrs_version: str | None
    # The AI marking the student saw before grading (ADR 0029), if any.
    ai_marking: AIMarking | None
    # The state and due this review led to: the practice screen's "next due" (null for
    # reviews from before scheduling).
    after: "ReviewAfterOut | None"


# --- FSRS scheduling and the queue (decision 0026) ------------------------------------

MemoryStateName = Literal["new", "learning", "review", "relearning"]


class Estimate(BaseModel):
    """A number shown to the student: always estimated here, with its sample size."""

    value: float
    label: Literal["estimated"] = "estimated"
    # Reviews it rests on.
    sample_size: int


class MemoryOut(BaseModel):
    state: MemoryStateName
    due: datetime | None
    stability: float | None
    difficulty: float | None
    # FSRS's R at the time of the request: the estimated chance of recalling it now.
    retrievability: Estimate | None
    reps: int
    lapses: int


ItemOut.model_rebuild()


class ReviewAfterOut(BaseModel):
    state: Literal["learning", "review", "relearning"]
    due: datetime


ReviewOut.model_rebuild()


class ScheduledOut(BaseModel):
    state: MemoryStateName
    due: datetime
    scheduled_days: int


class QueueCounts(BaseModel):
    # Active items due now.
    due_now: int
    # New items that can still be reviewed today: the allowance left, but no more than the new
    # items there are (0 with no new items, however much allowance is left).
    new_today_left: int
    # The allowance left: practice_new_per_day less the new items first reviewed today
    # (local day), never below 0.
    new_allowance_left: int
    # Active items never reviewed.
    new_total: int
    # The earliest due time after now, for "next review in 3 h".
    next_due_at: datetime | None


class QueueOut(BaseModel):
    items: list[ItemOut]
    counts: QueueCounts


class ReviewResultOut(BaseModel):
    review: ReviewOut
    scheduled: ScheduledOut
    counts: QueueCounts


GradeName = Literal["again", "hard", "good", "easy"]


class PreviewOption(BaseModel):
    grade: int
    name: GradeName
    due: datetime
    # "1 min", "10 min", "1 day", "4 days".
    interval: str


class PreviewOut(BaseModel):
    at: datetime
    options: list[PreviewOption]


Retention = Annotated[float, Field(ge=0.8, le=0.97)]
NewPerDay = Annotated[int, Field(ge=0, le=200)]


class PracticeSettingsOut(BaseModel):
    new_per_day: int
    desired_retention: float


class PracticeSettingsUpdate(_Update):
    new_per_day: NewPerDay | None = None
    desired_retention: Retention | None = None
