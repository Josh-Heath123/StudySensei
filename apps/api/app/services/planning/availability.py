"""Availability: weekly windows and per-date exceptions, expanded into real free time.

Pure functions only: no database, no clock. Windows are minutes after local midnight in the
user's timezone (``0 <= start < end <= 1440``; 1440 is the next midnight, so a window never
crosses it). Expansion turns each local window into a UTC interval for a date range:

- **Exceptions win.** A date with an exception uses its windows instead of the weekday's
  rules, or nothing if it's "unavailable all day".
- **DST-safe.** Each window's ends are converted on their own date with ``zoneinfo``, so the
  interval is the real elapsed time:
  - a local time that doesn't exist (clocks go forward) moves to the first one that does,
    so 00:30-03:00 on Europe/London's spring day is 1 h 30;
  - a local time that happens twice (clocks go back) is its first occurrence, so 00:30-03:00
    on the autumn day is 3 h 30.
- **The daily cap** limits how much of a day's free time the planner may use
  (``available_minutes``); the intervals themselves aren't cut.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from itertools import pairwise
from typing import Literal
from zoneinfo import ZoneInfo

MINUTES_PER_DAY = 1440


@dataclass(frozen=True, order=True)
class Window:
    """Minutes after local midnight: ``start`` inclusive, ``end`` exclusive."""

    start: int
    end: int


@dataclass(frozen=True)
class Rule:
    """A weekly window: ``weekday`` 0 is Monday (``date.weekday()``)."""

    weekday: int
    window: Window


@dataclass(frozen=True)
class DayException:
    """One date's override: unavailable all day, or these windows instead of the rules."""

    unavailable: bool
    windows: tuple[Window, ...] = ()


@dataclass(frozen=True)
class Interval:
    """A stretch of free time, in UTC."""

    start: datetime
    end: datetime

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


DaySource = Literal["rules", "exception", "unavailable"]


@dataclass(frozen=True)
class Day:
    date: date
    source: DaySource
    intervals: tuple[Interval, ...]
    # Real free time that day (DST included).
    free_minutes: int
    # What the planner may use: free time, at most the daily cap.
    available_minutes: int


def check_windows(windows: Iterable[Window]) -> list[Window]:
    """The windows sorted by start; ``ValueError`` if one is out of range, empty, or
    overlaps another (touching ends, like 09:00-12:00 and 12:00-13:00, is fine)."""
    ordered = sorted(windows)
    for window in ordered:
        if not 0 <= window.start < window.end <= MINUTES_PER_DAY:
            raise ValueError("A window must start before it ends, within one day.")
    for before, after in pairwise(ordered):
        if after.start < before.end:
            raise ValueError(
                f"Windows {format_minute(before.start)} to {format_minute(before.end)} and "
                f"{format_minute(after.start)} to {format_minute(after.end)} overlap."
            )
    return ordered


def format_minute(minute: int) -> str:
    """540 → "09:00"; 1440 → "24:00"."""
    return f"{minute // 60:02d}:{minute % 60:02d}"


def parse_minute(text: str) -> int:
    """ "09:00" → 540; "24:00" → 1440. ``ValueError`` for anything else."""
    hours, _, minutes = text.partition(":")
    if len(hours) != 2 or len(minutes) != 2 or not (hours + minutes).isdigit():
        raise ValueError("Use a time like 09:00.")
    value = int(hours) * 60 + int(minutes)
    if int(minutes) >= 60 or value > MINUTES_PER_DAY:
        raise ValueError("Use a time between 00:00 and 24:00.")
    return value


def _exists(local: datetime, tz: ZoneInfo) -> bool:
    """Whether a naive local time happens at all in ``tz`` (not skipped by clocks going
    forward)."""
    there_and_back = local.replace(tzinfo=tz).astimezone(UTC).astimezone(tz)
    return there_and_back.replace(tzinfo=None) == local


def local_to_utc(day: date, minute: int, tz: ZoneInfo) -> datetime:
    """The UTC instant of ``minute`` after local midnight on ``day`` (1440 is the next
    midnight). A skipped local time moves forward to the first one that exists; a repeated
    one is its first occurrence."""
    local = datetime.combine(day, time()) + timedelta(minutes=minute)
    # Gaps are at most a few hours (usually one); step to the first minute that exists.
    for _ in range(MINUTES_PER_DAY):
        if _exists(local, tz):
            break
        local += timedelta(minutes=1)
    return local.replace(tzinfo=tz, fold=0).astimezone(UTC)


def _intervals(day: date, windows: Sequence[Window], tz: ZoneInfo) -> tuple[Interval, ...]:
    out: list[Interval] = []
    for window in sorted(windows):
        interval = Interval(local_to_utc(day, window.start, tz), local_to_utc(day, window.end, tz))
        # A window wholly inside a skipped hour has no real time: drop it.
        if interval.end > interval.start:
            out.append(interval)
    return tuple(out)


def expand(
    rules: Iterable[Rule],
    exceptions: Mapping[date, DayException],
    first: date,
    last: date,
    tz: ZoneInfo,
    daily_cap_minutes: int,
) -> list[Day]:
    """Every local date from ``first`` to ``last`` (inclusive) with its free intervals in
    UTC, its free minutes, and the minutes available after the daily cap."""
    by_weekday: dict[int, list[Window]] = {}
    for rule in rules:
        by_weekday.setdefault(rule.weekday, []).append(rule.window)
    days: list[Day] = []
    day = first
    while day <= last:
        source: DaySource
        exception = exceptions.get(day)
        if exception is None:
            source, windows = "rules", by_weekday.get(day.weekday(), [])
        elif exception.unavailable:
            source, windows = "unavailable", []
        else:
            source, windows = "exception", list(exception.windows)
        intervals = _intervals(day, windows, tz)
        free = sum(interval.minutes for interval in intervals)
        days.append(Day(day, source, intervals, free, min(free, daily_cap_minutes)))
        day += timedelta(days=1)
    return days


def weekly_minutes(rules: Iterable[Rule], daily_cap_minutes: int) -> int:
    """A typical week from the rules alone (wall-clock minutes, no DST), each day capped."""
    totals = [0] * 7
    for rule in rules:
        totals[rule.weekday] += rule.window.end - rule.window.start
    return sum(min(total, daily_cap_minutes) for total in totals)
