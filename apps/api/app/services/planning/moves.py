"""Moving a block by hand (decision 0022). Pure: no database, no clock.

The block keeps its length and moves to ``start`` (on the 5-minute grid, checked by the
schema). The checks, in order, each with a sentence in ``explain.move_problem_text``:

- ``past``: it would start before now;
- ``after_deadline``: it would end after its assessment's due time;
- ``review_window``: a final review would start before the 3 days before its assessment
  (planner rule: the review is in those days; its text says "the last free time");
- ``outside_free_time``: it isn't inside one stretch of free time on its local day (skipped
  slots are already taken out of ``free`` by the caller);
- ``too_close``: less than the 10-minute break from another block of the current version;
- ``over_cap``: its local day's booked minutes, today's studied minutes if it's today, and
  this block would go over the daily cap.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from app.services.planning.availability import MINUTES_PER_DAY, Interval, local_to_utc
from app.services.planning.planner import BREAK_MINUTES, REVIEW_DAYS, Block

MoveProblemKind = Literal[
    "past", "outside_free_time", "too_close", "after_deadline", "review_window", "over_cap"
]


@dataclass(frozen=True)
class MoveProblem:
    kind: MoveProblemKind
    # The local date the block would move to.
    day: date
    # For after_deadline and review_window: the assessment's due time.
    due_at: datetime | None = None


def moved(block: Block, start: datetime) -> Block:
    """The block at ``start``, with the same length."""
    return replace(block, start=start, end=start + (block.end - block.start))


def _inside_one_day(
    start: datetime, end: datetime, free: Sequence[Interval], day: date, tz: ZoneInfo
) -> bool:
    """Whether [start, end) lies in the free time of local ``day`` (touching stretches
    merged, never across midnight)."""
    day_start, day_end = local_to_utc(day, 0, tz), local_to_utc(day, MINUTES_PER_DAY, tz)
    spans: list[tuple[datetime, datetime]] = []
    for interval in sorted(free, key=lambda i: (i.start, i.end)):
        s, e = max(interval.start, day_start), min(interval.end, day_end)
        if e <= s:
            continue
        if spans and s <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], e))
        else:
            spans.append((s, e))
    return any(s <= start and end <= e for s, e in spans)


def check_move(
    block: Block,
    start: datetime,
    *,
    now: datetime,
    free: Sequence[Interval],
    neighbours: Sequence[Block],
    booked: Sequence[Block],
    due_at: datetime,
    daily_cap_minutes: int,
    studied_on: Mapping[date, int],
    timezone: ZoneInfo,
) -> MoveProblem | None:
    """The first problem with moving ``block`` to ``start``, or None. ``neighbours`` are the
    current version's other blocks (for the break); ``booked`` are those that count against
    a day's cap."""
    target = moved(block, start)
    day = start.astimezone(timezone).date()
    if target.start < now:
        return MoveProblem("past", day)
    if target.end > due_at:
        return MoveProblem("after_deadline", day, due_at)
    if block.kind == "review" and target.start < due_at - timedelta(days=REVIEW_DAYS):
        return MoveProblem("review_window", day, due_at)
    if not _inside_one_day(target.start, target.end, free, day, timezone):
        return MoveProblem("outside_free_time", day)
    gap = timedelta(minutes=BREAK_MINUTES)
    for other in neighbours:
        if other.start < target.end + gap and target.start < other.end + gap:
            return MoveProblem("too_close", day)
    used = sum(b.minutes for b in booked if b.start.astimezone(timezone).date() == day)
    if used + studied_on.get(day, 0) + target.minutes > daily_cap_minutes:
        return MoveProblem("over_cap", day)
    return None
