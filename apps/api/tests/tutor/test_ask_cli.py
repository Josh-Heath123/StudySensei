"""``python -m app.tutor.ask --dry-run``: the real service, and nothing written."""

import io
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import AIUsage, Conversation, Message, User
from app.tutor.ask import Sessions, dry_run, parse
from tests.fakes import FakeLLM, ok, streamed
from tests.tutor.conftest import Module


def sessions_on(session: AsyncSession) -> Sessions:
    """The test session, with no lock: the dry run holds one session for the whole turn
    while the usage store counts today's calls in another (a sessionmaker in real use)."""

    @asynccontextmanager
    async def factory() -> AsyncIterator[AsyncSession]:
        yield session

    return factory


async def counts(session: AsyncSession) -> tuple[int, ...]:
    return tuple(
        [
            int(await session.scalar(select(func.count()).select_from(table)) or 0)
            for table in (Conversation, Message, AIUsage)
        ]
    )


async def test_a_dry_run_streams_the_answer_and_writes_nothing(
    session: AsyncSession, module: Module, settings: Settings, fake_llm: FakeLLM
) -> None:
    user = await session.get(User, module.user_id)
    assert user is not None
    local = settings.model_copy(update={"local_user_email": user.email})
    fake_llm.reply("flash", streamed("It tracks ", "each connection [S1]."))
    args = parse(
        [
            "--module",
            "cos330",
            "--topic",
            "microservices",
            "--dry-run",
            "How does a stateful firewall work?",
        ]
    )
    out = io.StringIO()

    result, calls = await dry_run(
        args, local, out, sessions_on(session), transport=fake_llm.transport
    )

    assert result is not None
    assert (result.status, result.model, result.cited) == ("complete", "gemini/flash", ["S1"])
    printed = out.getvalue()
    assert "S1 CH09 p1 · Stateful inspection" in printed
    assert "It tracks each connection [S1]." in printed
    assert "model gemini/flash" in printed
    assert [(c.provider, c.model, c.outcome) for c in calls] == [("gemini", "flash", "ok")]
    assert await counts(session) == (0, 0, 0)


async def test_an_unknown_topic_stops_before_any_call(
    session: AsyncSession, module: Module, settings: Settings, fake_llm: FakeLLM
) -> None:
    user = await session.get(User, module.user_id)
    assert user is not None
    local = settings.model_copy(update={"local_user_email": user.email})
    args = parse(["--module", "COS330", "--topic", "Nope", "--dry-run", "q"])

    with pytest.raises(SystemExit, match="one topic named 'Nope'"):
        await dry_run(
            args, local, io.StringIO(), sessions_on(session), transport=fake_llm.transport
        )
    assert fake_llm.requests == []


async def test_after_answers_the_earlier_question_then_the_follow_up_on_its_sources(
    session: AsyncSession, module: Module, settings: Settings, fake_llm: FakeLLM
) -> None:
    user = await session.get(User, module.user_id)
    assert user is not None
    local = settings.model_copy(update={"local_user_email": user.email})
    fake_llm.reply(
        "flash", streamed("It tracks connections [S1]."), streamed("Like a doorman [S1].")
    )
    args = parse(
        [
            "--module",
            "COS330",
            "--dry-run",
            "--mode",
            "explain_differently",
            "--after",
            "How does a stateful inspection firewall work?",
            "Explain that differently, as if to a first-year student",
        ]
    )
    out = io.StringIO()

    result, calls = await dry_run(
        args, local, out, sessions_on(session), transport=fake_llm.transport
    )

    assert result is not None and result.cited == ["S1"]
    assert len(calls) == 2
    first, second = (r.body["messages"] for r in fake_llm.requests)
    # The follow-up carries the earlier exchange and the very same source blocks.
    assert [m["role"] for m in second] == ["system", "user", "assistant", "user"]
    assert second[2]["content"] == "It tracks connections."
    blocks = first[-1]["content"].split("Student's question:")[0]
    assert blocks in second[-1]["content"]
    assert "Earlier question: How does a stateful inspection firewall work?" in out.getvalue()
    assert await counts(session) == (0, 0, 0)


async def test_quiz_mode_answers_then_quizzes_on_that_answers_sources(
    session: AsyncSession, module: Module, settings: Settings, fake_llm: FakeLLM
) -> None:
    user = await session.get(User, module.user_id)
    assert user is not None
    local = settings.model_copy(update={"local_user_email": user.email})
    question = {
        "prompt": "What does a stateful firewall track?",
        "options": ["Nothing", "Each connection", "Only ports", "Only addresses"],
        "correct": 1,
        "explanation": "It keeps a state table [S1].",
        "sources": ["S1"],
    }
    fake_llm.reply(
        "flash",
        streamed("It tracks connections [S1]."),
        ok(json.dumps({"questions": [question, {**question, "sources": ["S9"]}]})),
    )
    args = parse(
        ["--module", "COS330", "--dry-run", "--mode", "quiz", "--after", "How does it work?", "q"]
    )
    out = io.StringIO()

    result, calls = await dry_run(
        args, local, out, sessions_on(session), transport=fake_llm.transport
    )

    assert result is not None and result.status == "complete"
    printed = out.getvalue()
    assert "Quiz: 1 question(s), 1 dropped as ungrounded · model gemini/flash" in printed
    assert "  * B. Each connection" in printed
    assert "  S1: CH09 p1" in printed
    assert len(calls) == 2
    assert await counts(session) == (0, 0, 0)
