"""Planning inputs and outputs: settings, availability rules and exceptions, and a topic's
workload and confidence.

Times of day are "HH:MM" in the user's timezone; "24:00" is allowed as an end (the next
midnight). Stored as minutes after midnight (``app/models/planning.py``).
"""

import datetime as dt
import uuid
from typing import Annotated, Literal, Self
from zoneinfo import available_timezones

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.schemas.academics import WorkloadOut, _Input, _Update
from app.services.planning.availability import Window, check_windows, parse_minute

MAX_RANGE_DAYS = 62


def _clock(value: str) -> str:
    parse_minute(value)  # ValueError → 422 with its message
    return value


Clock = Annotated[str, AfterValidator(_clock)]
Weekday = Annotated[int, Field(ge=0, le=6, description="0 is Monday, 6 is Sunday")]
DailyCap = Annotated[int, Field(ge=15, le=1440)]
# Minutes before a block that its push reminder comes (decision 0024); null is off.
ReminderMinutes = Literal[5, 10, 15, 30]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Minutes = Annotated[int, Field(ge=5, le=6000)]
Confidence = Annotated[int, Field(ge=1, le=5)]


def _timezone(value: str) -> str:
    if value not in _ZONES:
        raise ValueError("Use an IANA timezone, like Africa/Johannesburg.")
    return value


_ZONES = frozenset(available_timezones())
Timezone = Annotated[str, AfterValidator(_timezone)]


# --- settings --------------------------------------------------------------------------


class PlanningSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timezone: str
    daily_study_cap_minutes: int
    reminder_minutes: ReminderMinutes | None


class PlanningSettingsUpdate(_Update):
    nullable = frozenset({"reminder_minutes"})

    timezone: Timezone | None = None
    daily_study_cap_minutes: DailyCap | None = None
    reminder_minutes: ReminderMinutes | None = None


# --- windows, rules and exceptions -----------------------------------------------------


class WindowIn(_Input):
    start: Clock
    end: Clock

    def minutes(self) -> Window:
        return Window(parse_minute(self.start), parse_minute(self.end))

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        check_windows([self.minutes()])
        return self


class WindowOut(BaseModel):
    start: str
    end: str


class RuleCreate(WindowIn):
    weekday: Weekday


class RuleUpdate(_Update):
    """Any of the three; the window is checked again once merged with what's stored."""

    weekday: Weekday | None = None
    start: Clock | None = None
    end: Clock | None = None


class RuleOut(WindowOut):
    id: uuid.UUID
    weekday: int


def _exception_windows(unavailable: bool, windows: list[WindowIn]) -> None:
    if unavailable and windows:
        raise ValueError("An unavailable day has no windows.")
    if not unavailable and not windows:
        raise ValueError("Add at least one window, or mark the day unavailable.")
    check_windows(window.minutes() for window in windows)


class ExceptionCreate(_Input):
    date: dt.date
    unavailable: bool = False
    windows: list[WindowIn] = Field(default_factory=list, max_length=12)
    note: Note | None = None

    @model_validator(mode="after")
    def _windows(self) -> Self:
        _exception_windows(self.unavailable, self.windows)
        return self


class ExceptionUpdate(_Update):
    """``unavailable`` and ``windows`` are checked together once merged with what's stored."""

    nullable = frozenset({"note"})

    date: dt.date | None = None
    unavailable: bool | None = None
    windows: list[WindowIn] | None = Field(default=None, max_length=12)
    note: Note | None = None


class ExceptionOut(BaseModel):
    id: uuid.UUID
    date: dt.date
    unavailable: bool
    windows: list[WindowOut]
    note: str | None


# --- expanded availability -------------------------------------------------------------


class IntervalOut(BaseModel):
    start: dt.datetime
    end: dt.datetime
    minutes: int


class AvailabilityDayOut(BaseModel):
    date: dt.date
    weekday: int
    # Where the day's time came from: its weekday's rules, an exception's windows, or an
    # exception marking it unavailable.
    source: Literal["rules", "exception", "unavailable"]
    intervals: list[IntervalOut]
    free_minutes: int
    # Free minutes, at most the daily cap: what the planner may use.
    available_minutes: int


class AvailabilityOut(BaseModel):
    timezone: str
    daily_study_cap_minutes: int
    days: list[AvailabilityDayOut]
    total_free_minutes: int
    total_available_minutes: int
    # A typical week from the rules alone, each day capped (no exceptions, no DST).
    weekly_minutes_from_rules: int


# --- a topic's workload and confidence ---------------------------------------------------


class TopicPlanningUpdate(_Update):
    nullable = frozenset({"estimated_minutes", "confidence"})

    # The student's own figure; null goes back to the estimate from the pages.
    estimated_minutes: Minutes | None = None
    # Self-rated, 1 to 5; null is "not rated".
    confidence: Confidence | None = None


class TopicPlanningOut(BaseModel):
    topic_id: uuid.UUID
    confidence: int | None
    workload: WorkloadOut


# --- plan preview (computed on request, nothing stored) ----------------------------------

Status = Literal["fits", "tight", "short"]


class PlanBlockOut(BaseModel):
    start: dt.datetime
    end: dt.datetime
    minutes: int
    module_id: uuid.UUID
    module_code: str
    module_colour: str
    assessment_id: uuid.UUID
    assessment_title: str
    # Null for a review, which covers all of the assessment's topics.
    topic_id: uuid.UUID | None
    topic_name: str | None
    kind: Literal["study", "review"]
    reason: Literal[
        "final_review",
        "spacing",
        "no_estimate",
        "low_confidence",
        "low_mastery",
        "urgency",
        "workload",
    ]
    method: Literal["mixed_review", "first_pass", "active_recall", "practice"]
    # Written by code from the block's facts (decision 0018), never by AI.
    reason_text: str
    method_text: str


class TopicFeasibilityOut(BaseModel):
    topic_id: uuid.UUID
    topic_name: str
    required_minutes: int
    planned_minutes: int
    short_minutes: int


class IssueOut(BaseModel):
    kind: Literal["not_enough_time", "not_spaced", "no_estimate", "no_review_time", "no_topics"]
    topic_id: uuid.UUID | None
    text: str


class FeasibilityNumbersOut(BaseModel):
    # Estimated: workload (yours or from pages) less measured study, scaled by confidence.
    required_minutes: int
    planned_minutes: int
    # Per topic max(0, required - planned), summed.
    short_minutes: int
    review_minutes: int
    # From now to the deadline, each local day at most the daily cap.
    free_minutes: int
    # Every block (any assessment's) that starts before the deadline.
    booked_minutes: int
    # short: anything short; tight: under 15 % of free time left over; else fits.
    status: Status


class AssessmentFeasibilityOut(FeasibilityNumbersOut):
    assessment_id: uuid.UUID
    title: str
    module_code: str
    due_at: dt.datetime
    line: str
    topics: list[TopicFeasibilityOut]
    issues: list[IssueOut]
    # When all its topics are planned for sooner assessments: those assessments (decision 0019).
    planned_with: list[uuid.UUID] = Field(default_factory=list)


class OverallFeasibilityOut(FeasibilityNumbersOut):
    # The last planned deadline, or null when nothing is due in the window.
    deadline: dt.datetime | None
    line: str


class LeverOut(BaseModel):
    kind: Literal["add_time", "raise_cap", "narrow_topics"]
    assessment_id: uuid.UUID | None
    text: str


class LaterAssessmentOut(BaseModel):
    assessment_id: uuid.UUID
    title: str
    module_code: str
    due_at: dt.datetime
    text: str


class FeasibilityOut(BaseModel):
    overall: OverallFeasibilityOut
    assessments: list[AssessmentFeasibilityOut]
    # Upcoming assessments due after the window: not planned yet.
    later: list[LaterAssessmentOut]
    levers: list[LeverOut]
    # What "needed" and "free" are based on.
    basis: str


class PlanPreviewOut(BaseModel):
    generated_at: dt.datetime
    timezone: str
    days: int
    # The local dates the plan covers (inclusive).
    first: dt.date
    last: dt.date
    daily_study_cap_minutes: int
    blocks: list[PlanBlockOut]
    feasibility: FeasibilityOut


# --- stored plans (decision 0021) ------------------------------------------------------


class BlockActionsOut(BaseModel):
    """What the student can do with a block now, decided by the server (decision 0022)."""

    # Start a session for it: planned in the current version, not ended, no session open.
    start: bool
    # Skip it: planned in the current version, and no open session linked to it.
    skip: bool
    # Move it: planned in the current version, not started, and no session linked to it.
    move: bool


class StoredBlockOut(BaseModel):
    id: uuid.UUID
    # When it's shown: the plan's times, or for a done block its linked session's measured
    # start and end (decision 0023). ``minutes`` is their length.
    start: dt.datetime
    end: dt.datetime
    minutes: int
    # The plan's times, always.
    planned_start: dt.datetime
    planned_end: dt.datetime
    module_id: uuid.UUID
    module_code: str
    module_colour: str
    assessment_id: uuid.UUID
    assessment_title: str
    topic_id: uuid.UUID | None
    topic_name: str | None
    kind: Literal["study", "review"]
    reason: Literal[
        "final_review",
        "spacing",
        "no_estimate",
        "low_confidence",
        "low_mastery",
        "urgency",
        "workload",
    ]
    method: Literal["mixed_review", "first_pass", "active_recall", "practice"]
    # As generated for this block's version (code-written, no AI).
    reason_text: str
    method_text: str
    # "missed" also for a current planned block that ended with no session (derived on read).
    status: Literal["planned", "done", "skipped", "missed"]
    status_changed_at: dt.datetime | None
    # Carried from the previous version (it started within the next 24 h, or is pinned).
    fixed: bool
    # The student moved it; re-plans keep it at its time while it's valid.
    pinned: bool
    # The session started for it, if any (the latest).
    linked_session_id: uuid.UUID | None
    # Measured: the linked session's active minutes, floored, for a done block.
    session_minutes: int | None
    actions: BlockActionsOut


class PlanVersionOut(BaseModel):
    number: int
    trigger: Literal[
        "initial",
        "skip",
        "finish",
        "assessment",
        "topic",
        "availability",
        "material",
        "nightly",
        "manual",
        "move",
        "practice",
    ]
    # Why this version exists, in one code-written sentence.
    summary: str
    generated_at: dt.datetime
    # When a re-plan last confirmed it (a re-plan that changes nothing writes no version).
    checked_at: dt.datetime
    timezone: str
    days: int
    # The feasibility report, as GET /plan/preview gives it, from the last check.
    report: FeasibilityOut


class PlanOut(PlanVersionOut):
    # The local dates asked for (inclusive).
    first: dt.date
    last: dt.date
    # The current version's blocks that overlap those dates, and done, skipped and missed
    # blocks from any version (the history), by start.
    blocks: list[StoredBlockOut]
    # A re-plan is queued or running: the plan may change shortly.
    replan_pending: bool


class BlockMoveIn(_Input):
    # On the 5-minute grid; must carry a timezone.
    start: AwareDatetime

    @field_validator("start")
    @classmethod
    def _on_the_grid(cls, value: dt.datetime) -> dt.datetime:
        if value.second or value.microsecond or value.minute % 5:
            raise ValueError("Choose a time on the 5-minute grid.")
        return value
