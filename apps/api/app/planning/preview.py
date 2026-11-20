"""Print the plan preview for the local user as a timetable, by local day, and the feasibility
report. The same plan as ``GET /plan/preview``, computed now and never stored (read-only: the
transaction is rolled back).

Run with: uv run python -m app.planning.preview --days 28 [--now 2026-11-20T08:00:00+02:00]

Dev only: ``--persist`` instead re-plans for real (``replan``, trigger manual, decision 0021)
and prints the stored version and its blocks; ``--skip-next`` then skips the next planned
block through the service and prints the version that follows. Both write to the database.
"""

import argparse
import asyncio
import sys
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.models import User
from app.schemas.planning import MAX_RANGE_DAYS, PlanOut, PlanPreviewOut
from app.services.planning import stored
from app.services.planning.explain import duration
from app.services.planning.inputs import DEFAULT_DAYS
from app.services.planning.preview import preview
from app.services.planning.replan import replan, skip_block

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


def render_version(plan: PlanOut) -> str:
    """A stored version: its number, trigger and summary, then its blocks by local day with
    their status, then the report's overall line."""
    tz = ZoneInfo(plan.timezone)
    lines = [
        f"Version {plan.number} ({plan.trigger}): {plan.summary}",
        f"  generated {plan.generated_at.astimezone(tz):%Y-%m-%d %H:%M}, "
        f"checked {plan.checked_at.astimezone(tz):%Y-%m-%d %H:%M}",
    ]
    day: date | None = None
    for block in plan.blocks:
        start, end = block.start.astimezone(tz), block.end.astimezone(tz)
        if start.date() != day:
            day = start.date()
            lines.append(_day(day))
        what = block.topic_name or "Final review"
        flags = block.status + (", fixed" if block.fixed else "")
        lines.append(
            f"  {start:%H:%M}-{end:%H:%M}  {block.module_code} {block.assessment_title} · {what}"
            f"  [{flags}; {block.reason}, {block.method}]"
        )
        lines.append(f"      Why: {block.reason_text}")
    if not plan.blocks:
        lines.append("  No blocks.")
    lines.append(f"  {plan.report.overall.line}")
    return "\n".join(lines)


async def main(days: int, now: datetime, *, persist: bool, skip_next: bool) -> None:
    email = get_settings().local_user_email
    async with get_sessionmaker()() as session:
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            raise SystemExit("No local user: run `python -m app.seed` first.")
        if not persist:
            result = await preview(session, user_id=user.id, now=now, days=days)
            await session.rollback()
            print(render(result))
        else:
            first = now.astimezone(ZoneInfo(user.timezone)).date()
            last = first + timedelta(days=min(days, MAX_RANGE_DAYS) - 1)
            await replan(session, user_id=user.id, now=now, trigger="manual")
            shown = await stored.plan_for(session, user_id=user.id, now=now, first=first, last=last)
            print(render_version(shown))
            if skip_next:
                upcoming = await stored.next_block(session, user_id=user.id, now=now)
                if upcoming is None:
                    print("\nNo planned block to skip.")
                else:
                    await skip_block(session, upcoming.id, user_id=user.id, now=now)
                    after = await stored.plan_for(
                        session, user_id=user.id, now=now, first=first, last=last
                    )
                    print()
                    print(render_version(after))
    await get_engine().dispose()


def cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="1 to 62 (default 28)")
    parser.add_argument("--now", type=datetime.fromisoformat, default=None, help="ISO time")
    parser.add_argument(
        "--persist", action="store_true", help="dev only: re-plan for real and print the version"
    )
    parser.add_argument(
        "--skip-next",
        action="store_true",
        help="with --persist: skip the next planned block, then print the new version",
    )
    args = parser.parse_args()
    if not 1 <= args.days <= MAX_RANGE_DAYS:
        parser.error(f"--days must be 1 to {MAX_RANGE_DAYS}")
    now = args.now or datetime.now(UTC)
    if now.tzinfo is None:
        parser.error("--now needs a UTC offset, like 2026-11-20T08:00:00+02:00")
    # The text has "≈" and "→"; Windows consoles default to a code page without them.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.skip_next and not args.persist:
        parser.error("--skip-next needs --persist")
    asyncio.run(main(args.days, now, persist=args.persist, skip_next=args.skip_next))


if __name__ == "__main__":
    cli()
