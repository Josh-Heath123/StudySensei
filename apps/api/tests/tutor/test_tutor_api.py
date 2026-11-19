"""The tutor over HTTP: conversations, and answers streamed as server-sent events."""

import asyncio
import json
import uuid
from collections.abc import MutableMapping
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models import AIUsage, Message, MessageSource, User
from tests.api.conftest import TEST_USER_HEADER, ClientFactory
from tests.fakes import (
    FakeLLM,
    StreamedBody,
    overloaded,
    rate_limited,
    stream_events,
    streamed,
)
from tests.tutor.conftest import FIREWALL, PRIVATE, Module, sse_events

QUESTION = {"question": "How does a stateful inspection firewall work?", "mode": "answer"}


async def start(api: httpx.AsyncClient, module: Module, **body: Any) -> dict[str, Any]:
    response = await api.post(f"/modules/{module.module_id}/tutor/conversations", json=body)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


async def ask(
    api: httpx.AsyncClient, conversation_id: str, body: dict[str, Any] = QUESTION
) -> list[tuple[str, dict[str, Any]]]:
    response = await api.post(f"/conversations/{conversation_id}/messages", json=body)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    return sse_events(response.text)


async def alice_client(client_as: ClientFactory, session: AsyncSession, module: Module) -> Any:
    user = await session.get(User, module.user_id)
    assert user is not None
    return client_as(user)


# --- conversations ---


async def test_a_conversation_for_a_session_takes_the_sessions_topic(
    client_as: ClientFactory, session: AsyncSession, module: Module
) -> None:
    async with await alice_client(client_as, session, module) as api:
        created = await start(api, module, study_session_id=str(module.study_id))
        read = await api.get(f"/conversations/{created['id']}")

    assert created["module_id"] == str(module.module_id)
    assert created["study_session_id"] == str(module.study_id)
    assert created["topic_id"] == str(module.topic_id)
    assert read.status_code == 200
    assert read.json() == created
    assert created["messages"] == []


async def test_a_conversation_can_have_neither_session_nor_topic(
    client_as: ClientFactory, session: AsyncSession, module: Module
) -> None:
    async with await alice_client(client_as, session, module) as api:
        created = await start(api, module)

    assert (created["study_session_id"], created["topic_id"]) == (None, None)


async def test_unknown_fields_and_empty_questions_are_rejected(
    client_as: ClientFactory, session: AsyncSession, module: Module, tutor_llm: object
) -> None:
    async with await alice_client(client_as, session, module) as api:
        bad = await api.post(
            f"/modules/{module.module_id}/tutor/conversations", json={"user_name": "Josh"}
        )
        created = await start(api, module)
        empty = await api.post(f"/conversations/{created['id']}/messages", json={"question": "   "})
        mode = await api.post(
            f"/conversations/{created['id']}/messages", json={"question": "x", "mode": "essay"}
        )

    assert (bad.status_code, empty.status_code, mode.status_code) == (422, 422, 422)


# --- the stream ---


async def test_sources_come_first_then_the_answer_then_done(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
) -> None:
    fake_llm.reply(
        "flash",
        streamed("It tracks ", "each connection [S1].", reasoning=["thinking"], output_tokens=7),
    )
    async with await alice_client(client_as, session, module) as api:
        created = await start(api, module, topic_id=str(module.topic_id))
        events = await ask(api, created["id"])
        read = (await api.get(f"/conversations/{created['id']}")).json()

    names = [name for name, _ in events]
    assert names == ["sources", "delta", "delta", "done"]
    sources = events[0][1]["sources"]
    assert sources[0] == {
        "label": "S1",
        "material_id": str(module.slides),
        "material_title": "CH09",
        "page_number": 1,
        "page_title": "Stateful inspection",
    }
    assert [s["label"] for s in sources] == [f"S{n}" for n in range(1, len(sources) + 1)]
    assert "".join(data["text"] for name, data in events if name == "delta") == (
        "It tracks each connection [S1]."
    )
    done = events[-1][1]
    assert done["status"] == "complete"
    assert done["model"] == "gemini/flash"
    assert done["cited"] == ["S1"]
    assert done["unknown_citations"] == []
    assert 0 <= done["first_token_ms"] <= done["total_ms"]

    question, reply = read["messages"]
    assert (question["role"], question["text"], question["status"]) == (
        "user",
        QUESTION["question"],
        "complete",
    )
    assert (question["model"], question["sources"]) == (None, [])
    assert reply["id"] == done["message_id"]
    assert (reply["role"], reply["status"], reply["model"]) == (
        "assistant",
        "complete",
        "gemini/flash",
    )
    assert reply["text"] == "It tracks each connection [S1]."
    assert reply["first_token_ms"] == done["first_token_ms"]
    assert [(s["label"], s["cited"]) for s in reply["sources"]] == [
        (s["label"], s["label"] == "S1") for s in sources
    ]


async def test_material_with_ai_off_is_never_a_source_nor_sent(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
) -> None:
    fake_llm.reply("flash", streamed("It tracks connections [S1]."))
    async with await alice_client(client_as, session, module) as api:
        created = await start(api, module)
        events = await ask(api, created["id"])

    sources = events[0][1]["sources"]
    assert str(module.private) not in {s["material_id"] for s in sources}
    sent = fake_llm.sent_text()
    assert FIREWALL[:40] in sent
    assert "MY OWN ANSWER" not in sent and PRIVATE[:20] not in sent
    assert "u00000000" not in sent


async def test_a_busy_model_before_the_first_token_hands_over(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
) -> None:
    fake_llm.reply("flash", overloaded())
    fake_llm.reply("oss-120b", streamed("From Groq [S1]."))
    async with await alice_client(client_as, session, module) as api:
        created = await start(api, module)
        events = await ask(api, created["id"])

    assert [name for name, _ in events] == ["sources", "delta", "done"]
    assert events[-1][1]["model"] == "groq/oss-120b"


async def test_a_failure_after_the_first_token_keeps_the_text_and_reports_an_error(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
) -> None:
    body = StreamedBody(stream_events("It tracks ", "never sent"), fail_after=1)
    fake_llm.reply("flash", streamed(body=body))
    async with await alice_client(client_as, session, module) as api:
        created = await start(api, module)
        events = await ask(api, created["id"])
        reply = (await api.get(f"/conversations/{created['id']}")).json()["messages"][1]

    assert [name for name, _ in events] == ["sources", "delta", "error"]
    error = events[-1][1]
    assert "stopped part-way" in error["message"]
    assert error["message_id"] == reply["id"]
    assert (reply["status"], reply["text"], reply["model"]) == (
        "failed",
        "It tracks ",
        "gemini/flash",
    )
    assert [r.model for r in fake_llm.requests] == ["flash"]  # no second model spliced in


async def test_when_every_model_is_busy_the_error_says_when_to_retry(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
) -> None:
    fake_llm.reply("flash", overloaded())
    fake_llm.reply("oss-120b", rate_limited(retry_after=40))
    async with await alice_client(client_as, session, module) as api:
        created = await start(api, module)
        events = await ask(api, created["id"])
        reply = (await api.get(f"/conversations/{created['id']}")).json()["messages"][1]

    assert [name for name, _ in events] == ["sources", "error"]
    error = events[-1][1]
    assert "Trying again after" in error["message"]
    assert error["retry_at"] is not None
    assert (reply["status"], reply["text"], reply["model"]) == ("failed", "", None)


async def test_an_answer_cut_off_at_the_output_limit_is_truncated(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
) -> None:
    fake_llm.reply("flash", streamed("A long answer [S1]", finish_reason="length"))
    async with await alice_client(client_as, session, module) as api:
        created = await start(api, module)
        events = await ask(api, created["id"])
        reply = (await api.get(f"/conversations/{created['id']}")).json()["messages"][1]

    assert events[-1][0] == "done"
    assert events[-1][1]["status"] == "truncated"
    assert reply["status"] == "truncated"


async def test_when_every_model_refuses_the_error_says_so(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
) -> None:
    fake_llm.reply("flash", streamed(finish_reason="content_filter"))
    fake_llm.reply("oss-120b", streamed())
    async with await alice_client(client_as, session, module) as api:
        created = await start(api, module)
        events = await ask(api, created["id"])

    assert [name for name, _ in events] == ["sources", "error"]
    assert "declined" in events[-1][1]["message"]
    assert events[-1][1]["retry_at"] is None


@pytest.mark.parametrize(
    ("reply", "cited", "unknown"),
    [
        ("Each connection is tracked [S1][S2].", ["S1", "S2"], []),
        ("See [S2, S1] and also [S9].", ["S1", "S2"], ["S9"]),
        ("The sources don't cover this.", [], []),
    ],
)
async def test_citations_are_stored_and_unknown_labels_flagged(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
    reply: str,
    cited: list[str],
    unknown: list[str],
) -> None:
    fake_llm.reply("flash", streamed(reply))
    async with await alice_client(client_as, session, module) as api:
        created = await start(api, module)
        events = await ask(api, created["id"])
        stored = (await api.get(f"/conversations/{created['id']}")).json()["messages"][1]

    done = events[-1][1]
    assert (done["cited"], done["unknown_citations"]) == (cited, unknown)
    assert stored["text"] == reply  # never rewritten
    assert stored["unknown_citations"] == unknown
    assert [s["label"] for s in stored["sources"] if s["cited"]] == cited


async def test_each_attempt_is_one_usage_row_without_any_text(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
) -> None:
    fake_llm.reply("flash", overloaded())
    fake_llm.reply("oss-120b", streamed("Tracked [S1].", output_tokens=4))
    async with await alice_client(client_as, session, module) as api:
        created = await start(api, module)
        await ask(api, created["id"])

    rows = (
        await session.execute(
            select(
                AIUsage.provider,
                AIUsage.model,
                AIUsage.role,
                AIUsage.purpose,
                AIUsage.outcome,
                AIUsage.output_tokens,
                AIUsage.detail,
            ).where(AIUsage.user_id == module.user_id)
        )
    ).all()
    assert sorted((p, m, r, pu, o, t) for p, m, r, pu, o, t, _ in rows) == [
        ("gemini", "flash", "smart", "tutor", "overloaded", 0),
        ("groq", "oss-120b", "smart", "tutor", "ok", 4),
    ]
    assert "Tracked" not in str(rows) and "stateful" not in str(rows)


async def test_the_last_two_exchanges_ride_along_without_their_labels(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
) -> None:
    fake_llm.reply(
        "flash",
        streamed("First answer [S1]."),
        streamed("Second answer [S2]."),
        streamed("Third answer."),
    )
    # Flash allows three a day in these settings, so Groq takes the fourth.
    fake_llm.reply("oss-120b", streamed("Fourth answer."))
    async with await alice_client(client_as, session, module) as api:
        created = await start(api, module)
        for n in ("first", "second", "third", "fourth"):
            await ask(api, created["id"], {"question": f"The {n} question about firewalls"})

    last = fake_llm.requests[-1].body["messages"]
    roles = [m["role"] for m in last]
    assert roles == ["system", "user", "assistant", "user", "assistant", "user"]
    assert last[1]["content"] == "Student's question: The second question about firewalls"
    assert last[2]["content"] == "Second answer."  # [S2] meant that turn's source
    assert last[4]["content"] == "Third answer."
    assert "The fourth question" in last[5]["content"]
    assert "<material" in last[5]["content"]


# --- the student leaves part-way ---


async def test_a_disconnect_stops_the_provider_and_stores_the_partial_answer(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
) -> None:
    body = StreamedBody(stream_events("It tracks ", "never sent"), pause_after=1)
    fake_llm.reply("flash", streamed(body=body))
    async with await alice_client(client_as, session, module) as api:
        conversation_id = (await start(api, module))["id"]

    # A raw ASGI call, so the client can hang up once the first piece arrives.
    request = json.dumps(QUESTION).encode()
    hung_up = asyncio.Event()
    received: list[bytes] = []
    requested = False

    async def receive() -> dict[str, Any]:
        nonlocal requested
        if not requested:
            requested = True
            return {"type": "http.request", "body": request, "more_body": False}
        await hung_up.wait()
        return {"type": "http.disconnect"}

    async def send(message: MutableMapping[str, Any]) -> None:
        if message["type"] == "http.response.body":
            received.append(message.get("body", b""))
            if b"event: delta" in message.get("body", b""):
                hung_up.set()

    path = f"/conversations/{conversation_id}/messages"
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [
            (b"content-type", b"application/json"),
            (TEST_USER_HEADER.lower().encode(), str(module.user_id).encode()),
        ],
        "client": ("test", 1),
        "server": ("test", 80),
    }
    await asyncio.wait_for(app(scope, receive, send), timeout=10)

    assert b"never sent" not in b"".join(received)
    assert body.closed  # the provider's stream was stopped
    reply = await session.scalar(
        select(Message).where(
            Message.conversation_id == uuid.UUID(conversation_id), Message.role == "assistant"
        )
    )
    assert reply is not None
    assert (reply.status, reply.text, reply.model) == ("stopped", "It tracks ", "gemini/flash")
    assert reply.first_token_ms is not None
    sources = await session.scalar(
        select(MessageSource.label).where(MessageSource.message_id == reply.id).limit(1)
    )
    assert sources == "S1"
    outcome = await session.scalar(select(AIUsage.outcome).where(AIUsage.user_id == module.user_id))
    assert outcome == "stopped"
