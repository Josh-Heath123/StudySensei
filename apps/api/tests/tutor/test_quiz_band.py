"""Quiz me and mastery (ADR 0031): when the conversation's topic has an estimated mastery, the
quiz prompt gets its band word and what to ask for, and nothing else about the student;
otherwise the prompt is unchanged."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.schemas.practice import ItemCreate, ReviewIn
from app.services.practice import items
from app.services.practice.reviewing import review_item
from app.services.tutor.prompts import PromptSource
from app.services.tutor.quiz import BAND_ASKS, quiz_messages
from tests.api.conftest import ClientFactory
from tests.fakes import FakeLLM, streamed
from tests.tutor.conftest import Module
from tests.tutor.test_quiz import question, quiz_reply


async def practise(session: AsyncSession, module: Module, grades: list[int]) -> None:
    """One new card per grade on the module's topic, each reviewed once, a minute apart."""
    start = datetime.now(UTC) - timedelta(hours=1)
    for n, grade in enumerate(grades):
        created = await items.create_item(
            session,
            ItemCreate(
                module_id=module.module_id,
                topic_id=module.topic_id,
                kind="flashcard",
                prompt=f"What is idea number {n}?",
                answer="An answer.",
            ),
            user_id=module.user_id,
        )
        await review_item(
            session,
            created.id,
            ReviewIn(grade=grade),
            user_id=module.user_id,
            now=start + timedelta(minutes=n),
        )


async def quiz_prompt(
    client_as: ClientFactory, session: AsyncSession, module: Module, fake_llm: FakeLLM
) -> str:
    user = await session.get(User, module.user_id)
    assert user is not None
    async with client_as(user) as api:
        created = await api.post(
            f"/modules/{module.module_id}/tutor/conversations",
            json={"topic_id": str(module.topic_id)},
        )
        conversation_id = created.json()["id"]
        fake_llm.reply("flash", streamed("It tracks each connection [S1]."))
        await api.post(
            f"/conversations/{conversation_id}/messages",
            json={"question": "How does a stateful inspection firewall work?"},
        )
        fake_llm.reply("flash", quiz_reply(question(1), question(2), question(3)))
        response = await api.post(f"/conversations/{conversation_id}/quiz")
    assert response.status_code == 201, response.text
    messages: list[dict[str, Any]] = fake_llm.requests[-1].body["messages"]
    return "\n".join(str(m["content"]) for m in messages)


@pytest.mark.parametrize(
    ("grades", "band"),
    [([1, 1, 1], "weak"), ([4, 4, 4, 4, 4, 4, 4, 4], "strong")],
)
async def test_an_estimated_topic_sends_its_band_only(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
    grades: list[int],
    band: str,
) -> None:
    await practise(session, module, grades)
    sent = await quiz_prompt(client_as, session, module, fake_llm)
    assert f"Their practice on this topic reads as {band}. {BAND_ASKS[band]}" in sent  # type: ignore[index]
    # The band word, and nothing else about the student: no figures, no other band.
    assert "mastery" not in sent.lower() and "%" not in sent
    assert sum(sent.count(f"reads as {other}") for other in BAND_ASKS) == 1


async def test_without_enough_practice_the_prompt_is_unchanged(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
) -> None:
    await practise(session, module, [1, 1])  # 2 attempts: not enough, no band
    sent = await quiz_prompt(client_as, session, module, fake_llm)
    assert "reads as" not in sent
    for ask in BAND_ASKS.values():
        assert ask not in sent


def test_the_prompt_without_a_band_is_as_before() -> None:
    source = PromptSource("S1", "CH09 Firewalls", 1, "A stateful firewall tracks connections.")
    plain = quiz_messages([source], "How?")
    assert quiz_messages([source], "How?", None) == plain
    assert plain[1].text.endswith(
        "The student was asking: How?\n\nWrite the 3 questions on this, from these sources only."
    )
    weak = quiz_messages([source], "How?", "weak")[1].text
    assert weak.endswith(
        "The student was asking: How?\n\nTheir practice on this topic reads as weak. "
        f"{BAND_ASKS['weak']}\n\nWrite the 3 questions on this, from these sources only."
    )
