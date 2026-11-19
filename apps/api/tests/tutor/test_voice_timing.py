"""PATCH /messages/{id}/voice-timing: a spoken question's latency, measured in the browser."""

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from tests.api.conftest import ClientFactory
from tests.fakes import FakeLLM, streamed
from tests.tutor.conftest import Module, sse_events

TIMING = {
    "voice_latency_ms": 1900,
    "transcript_ms": 250,
    "first_token_ms": 900,
    "first_sentence_ms": 1500,
}


async def test_the_timing_is_stored_on_the_answer_and_comes_back(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
) -> None:
    user = await session.get(User, module.user_id)
    assert user is not None
    fake_llm.reply("flash", streamed("It tracks each connection [S1]."))
    async with client_as(user) as api:
        created = await api.post(f"/modules/{module.module_id}/tutor/conversations", json={})
        conversation_id = created.json()["id"]
        events = sse_events(
            (
                await api.post(
                    f"/conversations/{conversation_id}/messages",
                    json={"question": "How does a stateful firewall work?"},
                )
            ).text
        )
        answer_id = events[-1][1]["message_id"]
        saved = await api.patch(f"/messages/{answer_id}/voice-timing", json=TIMING)
        stored = (await api.get(f"/conversations/{conversation_id}")).json()["messages"]

    assert saved.status_code == 200
    assert saved.json()["voice_latency_ms"] == 1900
    assert saved.json()["voice_timing"] == {
        "transcript_ms": 250,
        "first_token_ms": 900,
        "first_sentence_ms": 1500,
    }
    assert stored[1]["voice_latency_ms"] == 1900
    assert stored[0]["voice_latency_ms"] is None  # the question has none


@pytest.mark.parametrize(
    "body",
    [
        {**TIMING, "voice_latency_ms": -1},
        {**TIMING, "first_token_ms": 600_001},
        {k: v for k, v in TIMING.items() if k != "transcript_ms"},
        {**TIMING, "audio": "never"},
    ],
)
async def test_a_bad_timing_is_rejected(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
    body: dict[str, Any],
) -> None:
    user = await session.get(User, module.user_id)
    assert user is not None
    fake_llm.reply("flash", streamed("Tracked [S1]."))
    async with client_as(user) as api:
        conversation_id = (
            await api.post(f"/modules/{module.module_id}/tutor/conversations", json={})
        ).json()["id"]
        events = sse_events(
            (
                await api.post(
                    f"/conversations/{conversation_id}/messages", json={"question": "Stateful?"}
                )
            ).text
        )
        response = await api.patch(
            f"/messages/{events[-1][1]['message_id']}/voice-timing", json=body
        )

    assert response.status_code == 422


async def test_only_an_answer_has_a_voice_timing(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
) -> None:
    user = await session.get(User, module.user_id)
    assert user is not None
    fake_llm.reply("flash", streamed("Tracked [S1]."))
    async with client_as(user) as api:
        conversation_id = (
            await api.post(f"/modules/{module.module_id}/tutor/conversations", json={})
        ).json()["id"]
        await api.post(f"/conversations/{conversation_id}/messages", json={"question": "Stateful?"})
        question = (await api.get(f"/conversations/{conversation_id}")).json()["messages"][0]
        response = await api.patch(f"/messages/{question['id']}/voice-timing", json=TIMING)

    assert (response.status_code, response.json()["detail"]) == (
        422,
        "Only an answer has a voice timing.",
    )
