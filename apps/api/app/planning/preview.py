"""Print the plan preview for the local user as a timetable, by local day, and the feasibility
report. The same plan as ``GET /plan/preview``, computed now and never stored (read-only: the
transaction is rolled back).

Run with: uv run python -m app.planning.preview --days 28 [--now 2026-11-20T08:00:00+02:00]
"""

import argparse
import asyncio
import sys
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.models import User
from app.schemas.planning import MAX_RANGE_DAYS, PlanPreviewOut
from app.services.planning.explain import duration
from app.services.planning.inputs import DEFAULT_DAYS
from app.services.planning.preview import preview

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _day(day: date) -> str:
    return f"{WEEKDAYS[day.weekday()]} {day.day} {MONTHS[day.month - 1]}"


def render(result: PlanPreviewOut) -> str:
    """The preview as plain text: blocks by local day, then the feasibility report."""
    tz = ZoneInfo(result.timezone)
    lines = [
        f"Plan for {_day(result.first)} to {_day(result.last)} ({result.timezone}, "
        f"daily cap {duration(result.daily_study_cap_minutes)})",
        "",
    ]
    by_day: dict[date, list[str]] = {}
    for block in result.blocks:
        start, end = block.start.astimezone(tz), block.end.astimezone(tz)
        what = block.topic_name or "Final review"
        rows = by_day.setdefault(start.date(), [])
        rows.append(
            f"  {start:%H:%M}-{end:%H:%M}  {block.module_code} {block.assessment_title} · {what}"
            f"  [{block.kind}, {block.reason}, {block.method}]"
        )
        rows.append(f"      Why: {block.reason_text}")
        rows.append(f"      How: {block.method_text}")
    if not by_day:
        lines.append("  No blocks.")
    for day in sorted(by_day):
        minutes = sum(b.minutes for b in result.blocks if b.start.astimezone(tz).date() == day)
        lines.append(f"{_day(day)} ({duration(minutes)})")
        lines.extend(by_day[day])
    report = result.feasibility
    lines += ["", "Feasibility", f"  {report.overall.line} Overall: {report.overall.status}."]
    lines.append(
        f"  Needed {duration(report.overall.required_minutes)}, planned "
        f"{duration(report.overall.planned_minutes)} (+ "
        f"{duration(report.overall.review_minutes)} review), free "
        f"{duration(report.overall.free_minutes)}, booked "
        f"{duration(report.overall.booked_minutes)}."
    )
    for assessment in report.assessments:
        lines.append(f"  - {assessment.line}")
        for issue in assessment.issues:
            lines.append(f"      {issue.text}")
    for later in report.later:
        lines.append(f"  - {later.text}")
    if report.levers:
        lines.append("  What you can change:")
        lines.extend(f"    - {lever.text}" for lever in report.levers)
    lines.append(f"  {report.basis}")
    return "\n".join(lines)


async def main(days: int, now: datetime) -> None:
    email = get_settings().local_user_email
    async with get_sessionmaker()() as session:
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            raise SystemExit("No local user: run `python -m app.seed` first.")
        result = await preview(session, user_id=user.id, now=now, days=days)
        await session.rollback()
    await get_engine().dispose()
    print(render(result))


def cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="1 to 62 (default 28)")
    parser.add_argument("--now", type=datetime.fromisoformat, default=None, help="ISO time")
    args = parser.parse_args()
    if not 1 <= args.days <= MAX_RANGE_DAYS:
        parser.error(f"--days must be 1 to {MAX_RANGE_DAYS}")
    now = args.now or datetime.now(UTC)
    if now.tzinfo is None:
        parser.error("--now needs a UTC offset, like 2026-11-20T08:00:00+02:00")
    # The text has "≈" and "→"; Windows consoles default to a code page without them.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main(args.days, now))


if __name__ == "__main__":
    cli()
