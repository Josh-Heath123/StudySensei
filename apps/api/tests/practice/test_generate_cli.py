"""``python -m app.practice.generate --dry-run``: the real service, printed, nothing written."""

import io
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import AIUsage, PracticeGeneration, PracticeItem, User
from app.practice.generate import dry_run, parse
from app.tutor.ask import Sessions
from tests.fakes import FakeLLM, ok
from tests.practice.conftest import Practice, card, generated


def sessions_on(session: AsyncSession) -> Sessions:
    @asynccontextmanager
    async def factory() -> AsyncIterator[AsyncSession]:
        yield session

    return factory


async def counts(session: AsyncSession) -> tuple[int, ...]:
    return tuple(
        [
            int(await session.scalar(select(func.count()).select_from(table)) or 0)
            for table in (PracticeItem, PracticeGeneration, AIUsage)
        ]
    )


async def test_a_dry_run_prints_and_writes_nothing(
    session: AsyncSession, practice: Practice, settings: Settings, fake_llm: FakeLLM
) -> None:
    user = await session.get(User, practice.user_id)
    assert user is not None
    local = settings.model_copy(update={"local_user_email": user.email})
    fake_llm.reply(
        "flash",
        ok(
            generated(
                card("What does a state table hold?", "Connections already seen.", ["S1"]),
                card("What is AES?", "A cipher.", ["S7"]),
            ),
            input_tokens=900,
            output_tokens=120,
        ),
    )
    args = parse(["--module", "cos330", "--topic", "microservices", "--count", "4", "--dry-run"])
    out = io.StringIO()

    code = await dry_run(args, local, out, sessions_on(session), transport=fake_llm.transport)

    assert code == 0
    printed = out.getvalue()
    assert "1. [flashcard] What does a state table hold?" in printed
    assert "S1: CH09 Firewalls p1" in printed
    assert "A stateful inspection firewall tracks each TCP connection" in printed
    assert "Requested 4 · returned 2 · kept 1 · dropped: not_grounded 1" in printed
    assert "Tokens: 900 in, 120 out" in printed and "model gemini/flash" in printed
    assert await counts(session) == (0, 0, 0)


def test_the_count_is_bounded() -> None:
    for bad in ("3", "13"):
        with pytest.raises(SystemExit):
            parse(["--module", "X", "--topic", "Y", "--count", bad])
