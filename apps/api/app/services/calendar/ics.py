"""The plan as an iCalendar file (decision 0024). Pure: events in, bytes out.

Each event's UID is its slot (``push.payload.slot_key``) ``@studysensei``, so a calendar app
keeps an unchanged block across plan versions and replaces one that moved. Times are UTC.
icalendar escapes commas, semicolons and newlines and folds long lines (RFC 5545).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from icalendar import Calendar, Event, vDuration

CALENDAR_NAME = "StudySensei plan"
REFRESH = timedelta(hours=1)
PRODID = "-//StudySensei//Plan//EN"


@dataclass(frozen=True)
class CalendarEvent:
    uid: str
    start: datetime
    end: datetime
    summary: str
    description: str


def event_summary(
    *, topic_name: str | None, module_code: str, assessment_title: str, done: bool = False
) -> str:
    """The event title: "Ch1 Overview · COS330", or "Final review · COS330 Exam"; "✓ " first
    when done."""
    name = (
        f"{topic_name} · {module_code}"
        if topic_name is not None
        else f"Final review · {module_code} {assessment_title}"
    )
    return f"✓ {name}" if done else name


def event_description(*, method_text: str, reason_text: str) -> str:
    return f"How: {method_text}\nWhy: {reason_text}"


def done_description(*, active_seconds: float) -> str:
    """A done block's description: what was measured, not the plan-time "How/Why".
    "Done · 48 min studied (measured).", or "Done · under 1 min studied (measured)."
    """
    minutes = int(active_seconds // 60)
    studied = "under 1 min" if minutes < 1 else f"{minutes} min"
    return f"Done · {studied} studied (measured)."


def build_calendar(events: Iterable[CalendarEvent], *, now: datetime) -> bytes:
    calendar = Calendar()
    calendar.add("prodid", PRODID)
    calendar.add("version", "2.0")
    calendar.add("calscale", "GREGORIAN")
    calendar.add("method", "PUBLISH")
    calendar.add("x-wr-calname", CALENDAR_NAME)
    calendar.add("refresh-interval", vDuration(REFRESH), parameters={"VALUE": "DURATION"})
    calendar.add("x-published-ttl", vDuration(REFRESH))
    stamp = now.astimezone(UTC)
    for item in events:
        event = Event()
        event.add("uid", item.uid)
        event.add("dtstamp", stamp)
        event.add("dtstart", item.start.astimezone(UTC))
        event.add("dtend", item.end.astimezone(UTC))
        event.add("summary", item.summary)
        event.add("description", item.description)
        calendar.add_component(event)
    ical: bytes = calendar.to_ical()
    return ical
