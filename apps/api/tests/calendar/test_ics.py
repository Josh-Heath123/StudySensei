"""The plan as an iCalendar file (decision 0024): parsed back with icalendar, escaping,
folding, and UIDs that hold for an unchanged block across a re-plan and change for a moved one."""

from datetime import UTC, datetime, timedelta

from icalendar import Calendar
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AvailabilityException, User
from app.services.calendar.feed import calendar_events
from app.services.calendar.ics import (
    CalendarEvent,
    build_calendar,
    event_description,
    event_summary,
)
from app.services.planning.replan import move_block, replan
from tests.planning.test_replan import NOW, setup

STAMP = datetime(2026, 11, 20, 7, 0, tzinfo=UTC)


def event(uid: str = "k@studysensei", **kw: object) -> CalendarEvent:
    base = {
        "uid": uid,
        "start": datetime(2026, 11, 21, 7, 0, tzinfo=UTC),
        "end": datetime(2026, 11, 21, 7, 50, tzinfo=UTC),
        "summary": "Ch1 Overview · COS330",
        "description": "How: Read.\nWhy: Because.",
    }
    return CalendarEvent(**{**base, **kw})  # type: ignore[arg-type]


def test_it_parses_back_with_the_calendar_properties() -> None:
    text = build_calendar([event()], now=STAMP)
    cal = Calendar.from_ical(text)
    assert cal["VERSION"] == "2.0"
    assert cal["X-WR-CALNAME"] == "StudySensei plan"
    lines = text.split(b"\r\n")
    assert b"REFRESH-INTERVAL;VALUE=DURATION:PT1H" in lines
    assert b"X-PUBLISHED-TTL:PT1H" in lines
    [vevent] = cal.walk("VEVENT")
    assert str(vevent["UID"]) == "k@studysensei"
    assert vevent.decoded("DTSTART") == datetime(2026, 11, 21, 7, 0, tzinfo=UTC)
    assert vevent.decoded("DTEND") == datetime(2026, 11, 21, 7, 50, tzinfo=UTC)
    assert vevent.decoded("DTSTAMP") == STAMP
    assert str(vevent["SUMMARY"]) == "Ch1 Overview · COS330"
    assert str(vevent["DESCRIPTION"]) == "How: Read.\nWhy: Because."


def test_times_are_utc() -> None:
    from zoneinfo import ZoneInfo

    local = datetime(2026, 11, 21, 9, 0, tzinfo=ZoneInfo("Africa/Johannesburg"))
    text = build_calendar([event(start=local, end=local + timedelta(minutes=50))], now=STAMP)
    assert b"DTSTART:20261121T070000Z" in text
    assert b"DTEND:20261121T075000Z" in text


def test_commas_semicolons_and_newlines_are_escaped() -> None:
    text = build_calendar(
        [event(summary="A, B; C", description="How: x, y; z\nWhy: w")], now=STAMP
    ).decode()
    assert "SUMMARY:A\\, B\\; C" in text
    assert "DESCRIPTION:How: x\\, y\\; z\\nWhy: w" in text
    [vevent] = Calendar.from_ical(text).walk("VEVENT")
    assert str(vevent["SUMMARY"]) == "A, B; C"


def test_long_lines_are_folded() -> None:
    long = "Why: " + "spaced practice " * 20
    text = build_calendar([event(description=long)], now=STAMP)
    assert all(len(line) <= 75 for line in text.split(b"\r\n"))
    [vevent] = Calendar.from_ical(text).walk("VEVENT")
    assert str(vevent["DESCRIPTION"]) == long


def test_summaries_and_descriptions() -> None:
    assert (
        event_summary(topic_name="Ch1 Overview", module_code="COS330", assessment_title="Exam")
        == "Ch1 Overview · COS330"
    )
    assert (
        event_summary(topic_name=None, module_code="COS330", assessment_title="Exam")
        == "Final review · COS330 Exam"
    )
    assert event_summary(
        topic_name="Ch1", module_code="COS330", assessment_title="Exam", done=True
    ).startswith("✓ Ch1")
    assert event_description(method_text="Read.", reason_text="Because.") == (
        "How: Read.\nWhy: Because."
    )


async def test_uids_hold_across_a_replan_and_change_for_a_moved_block(
    session: AsyncSession, user_a: User
) -> None:
    await setup(session, user_a)
    await replan(session, user_id=user_a.id, now=NOW, trigger="initial")
    first = {e.start: e.uid for e in await calendar_events(session, user_id=user_a.id, now=NOW)}
    assert first and all(uid.endswith("@studysensei") for uid in first.values())

    # A new version that keeps tonight's block (a fixed copy with a new id): same UID.
    session.add(
        AvailabilityException(
            user_id=user_a.id, date=(NOW + timedelta(days=2)).date(), unavailable=True, windows=[]
        )
    )
    await session.commit()
    second = await replan(session, user_id=user_a.id, now=NOW, trigger="availability")
    assert second.number == 2
    events = await calendar_events(session, user_id=user_a.id, now=NOW)
    tonight = min(first)
    assert {e.start: e.uid for e in events}[tonight] == first[tonight]

    # Moved, the block is a new slot: its old UID is gone and a new one appears.
    from sqlalchemy import select

    from app.models import PlanBlock

    block = await session.scalar(
        select(PlanBlock).where(PlanBlock.version_id == second.id, PlanBlock.start_at == tonight)
    )
    assert block is not None
    target = tonight + timedelta(hours=2)
    await move_block(session, block.id, target, user_id=user_a.id, now=NOW)
    moved = {e.start: e.uid for e in await calendar_events(session, user_id=user_a.id, now=NOW)}
    assert first[tonight] not in moved.values()
    assert target in moved


async def test_only_unended_planned_blocks_within_8_weeks(
    session: AsyncSession, user_a: User
) -> None:
    await setup(session, user_a)
    version = await replan(session, user_id=user_a.id, now=NOW, trigger="initial")
    assert version.number == 1
    events = await calendar_events(session, user_id=user_a.id, now=NOW)
    assert events
    later = await calendar_events(session, user_id=user_a.id, now=events[0].end)
    assert len(later) == len(events) - 1  # the first has ended
    assert all(e.start < NOW + timedelta(weeks=8) for e in events)
