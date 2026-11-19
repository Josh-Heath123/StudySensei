"""Deleting a study session deletes its tutor conversation, messages and sources (0019)."""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, Message, MessageSource, Topic, User
from tests.api.conftest import ClientFactory
from tests.fakes import FakeLLM, streamed
from tests.tutor.conftest import Module


async def count(session: AsyncSession, model: Any, user_id: uuid.UUID) -> int:
    return int(
        await session.scalar(
            select(func.count()).select_from(model).where(model.user_id == user_id)
        )
        or 0
    )


async def a_session_with_an_answer(
    client_as: ClientFactory, session: AsyncSession, module: Module, fake_llm: FakeLLM
) -> str:
    user = await session.get(User, module.user_id)
    assert user is not None
    fake_llm.reply("flash", streamed("It tracks each connection [S1]."))
    async with client_as(user) as api:
        created = await api.post(
            f"/modules/{module.module_id}/tutor/conversations",
            json={"study_session_id": str(module.study_id)},
        )
        conversation_id = str(created.json()["id"])
        await api.post(
            f"/conversations/{conversation_id}/messages",
            json={"question": "How does a stateful firewall work?"},
        )
    return conversation_id


async def test_deleting_a_session_deletes_its_conversation_and_everything_in_it(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
) -> None:
    conversation_id = await a_session_with_an_answer(client_as, session, module, fake_llm)
    assert await count(session, MessageSource, module.user_id) > 0
    user = await session.get(User, module.user_id)
    assert user is not None

    async with client_as(user) as api:
        deleted = await api.delete(f"/sessions/{module.study_id}")
        gone = await api.get(f"/conversations/{conversation_id}")
        listed = await api.get(f"/modules/{module.module_id}/tutor/conversations")

    assert deleted.status_code == 204
    assert gone.status_code == 404
    assert listed.json() == []
    for model in (Conversation, Message, MessageSource):
        assert await count(session, model, module.user_id) == 0


async def test_another_users_delete_leaves_the_conversation_alone(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
    user_b: User,
) -> None:
    conversation_id = await a_session_with_an_answer(client_as, session, module, fake_llm)

    async with client_as(user_b) as bob:
        refused = await bob.delete(f"/sessions/{module.study_id}")

    assert refused.status_code == 404
    found = await session.get(Conversation, uuid.UUID(conversation_id))
    assert found is not None and found.study_session_id == module.study_id
    assert await count(session, Message, module.user_id) == 2


async def test_deleting_the_topic_keeps_the_conversation(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
) -> None:
    conversation_id = await a_session_with_an_answer(client_as, session, module, fake_llm)
    topic = await session.get(Topic, module.topic_id)
    assert topic is not None
    await session.delete(topic)
    await session.commit()

    found = await session.get(Conversation, uuid.UUID(conversation_id))
    await session.refresh(found)
    assert found is not None and found.topic_id is None
    assert await count(session, Message, module.user_id) == 2
