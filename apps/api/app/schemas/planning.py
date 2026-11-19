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
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
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


class PlanningSettingsUpdate(_Update):
    timezone: Timezone | None = None
    daily_study_cap_minutes: DailyCap | None = None


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
