"""The one clock (decision 0023). Routers, services, the worker and the CLIs ask ``now()``
instead of calling ``datetime.now(UTC)``.

``FAKE_NOW`` (an ISO time with a timezone) freezes it, so the demo's screenshots and their
browser agree on the date. Settings refuse it unless the database's name ends in ``_demo`` or
``_e2e``, so the API and the worker fail at startup rather than run a real plan on a fake day.
"""

from datetime import UTC, datetime

from app.core.config import get_settings


def now() -> datetime:
    """The current time in UTC, or ``FAKE_NOW`` on the demo and e2e databases."""
    fake = get_settings().fake_now
    return fake.astimezone(UTC) if fake is not None else datetime.now(UTC)
