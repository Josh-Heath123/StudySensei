"""Daily quota windows. Pure functions of the clock.

Free tiers count requests per day and reset at midnight in the provider's time zone
(Pacific for Gemini). The client counts its own ``ai_usage`` rows since the last reset
and stops using a model once its budget is spent, until the next reset.
"""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.config import Settings


def quota_zone(provider: str, settings: Settings) -> ZoneInfo:
    return ZoneInfo(settings.ai_quota_timezone.get(provider, "UTC"))


def window_start(now: datetime, zone: ZoneInfo) -> datetime:
    """The most recent local midnight in ``zone`` at or before ``now``, in UTC."""
    local = now.astimezone(zone)
    return datetime.combine(local.date(), time(0), tzinfo=zone).astimezone(UTC)


def next_reset(now: datetime, zone: ZoneInfo) -> datetime:
    """The next local midnight in ``zone`` after ``now``.

    Adding a calendar day to the local date (not 24 hours) keeps it right across
    daylight-saving changes. Returned in UTC, so arithmetic on it is in real hours.
    """
    local = now.astimezone(zone)
    return datetime.combine(local.date() + timedelta(days=1), time(0), tzinfo=zone).astimezone(UTC)
