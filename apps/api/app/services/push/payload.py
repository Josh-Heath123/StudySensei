"""What a reminder says, and the slot it's for (decision 0024). Pure.

The payload is encrypted end to end (RFC 8291), and still carries only a topic or assessment
name, a time, the block's length and its method: no reflections, notes or other personal data.
"""

import hashlib
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo


def slot_key(
    start: datetime, end: datetime, assessment_id: uuid.UUID, topic_id: uuid.UUID | None
) -> str:
    """A block's slot: sha256 of its start, end, assessment and topic. Blocks get new ids in
    every plan version, so the reminder for a block carried forward unchanged is found by its
    slot; a block that moved or was placed again is a new slot."""
    parts = (
        start.astimezone(ZoneInfo("UTC")).isoformat(),
        end.astimezone(ZoneInfo("UTC")).isoformat(),
        str(assessment_id),
        str(topic_id) if topic_id is not None else "",
    )
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def reminder_payload(
    *,
    topic_name: str | None,
    assessment_name: str,
    start: datetime,
    minutes: int,
    method_text: str,
    timezone: ZoneInfo,
    tag: str,
) -> dict[str, str]:
    """``{title, body, url, tag}``: "Ch1 Overview at 18:00" (or "Final review: COS330 Exam at
    18:00"), "50 min · <method>", the app's home page, and the slot as the tag, so a repeat
    replaces the earlier notification."""
    at = start.astimezone(timezone).strftime("%H:%M")
    name = topic_name if topic_name is not None else f"Final review: {assessment_name}"
    return {
        "title": f"{name} at {at}",
        "body": f"{minutes} min · {method_text}",
        "url": "/",
        "tag": tag,
    }


TEST_PAYLOAD = {
    "title": "Reminders work",
    "body": "You'll get one before each planned block.",
    "url": "/settings",
    "tag": "studysensei-test",
}
