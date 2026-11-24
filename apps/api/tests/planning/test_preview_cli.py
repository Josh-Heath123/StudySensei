"""``python -m app.planning.preview``: the preview as a timetable by local day, read-only."""

import sys
from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.models.base import TimestampedBase
from app.planning.preview import cli, render
from app.services.planning.preview import preview
from tests.academics.conftest import make_rows
from tests.planning.test_inputs import NOW, due_in, every_evening


async def test_the_timetable_and_report(session: AsyncSession, user_a: User) -> None:
    rows = await make_rows(session, user_a)
    await due_in(session, rows, 4)
    await every_evening(session, user_a)
    tables = [m.local_table for m in TimestampedBase.registry.mappers]
    before = [await session.scalar(select(func.count()).select_from(t)) for t in tables]

    text = render(await preview(session, user_id=user_a.id, now=NOW, days=7))

    lines = text.splitlines()
    assert lines[0] == "Plan for Fri 20 Nov to Thu 26 Nov (Africa/Johannesburg, daily cap 3 h)"
    assert "Fri 20 Nov (50 min)" in lines
    assert any(line.startswith("  18:00-18:50  COS330 Semester test 1 · ") for line in lines)
    assert any(line.startswith("      Why: ") for line in lines)
    assert any(line.startswith("      How: ") for line in lines)
    due = (NOW + timedelta(days=4)).day
    assert f"  You need 50 min before {due} Nov and have " in text
    assert "Feasibility" in lines
    # Nothing was written.
    after = [await session.scalar(select(func.count()).select_from(t)) for t in tables]
    assert after == before


def test_no_mastery_is_for_the_preview_only(monkeypatch: pytest.MonkeyPatch) -> None:
    # Dev only (ADR 0031): --no-mastery compares previews; it never writes a version.
    argv = ["preview", "--persist", "--no-mastery", "--now", "2026-11-20T08:00:00+02:00"]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit):
        cli()
