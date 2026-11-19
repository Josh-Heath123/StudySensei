"""Follow-ups keep their context; a session's conversation can be found again; startup preload.

Found live on 19 Nov: "Explain that differently, as if to a first-year student" was searched
on its own words, found other chapters, and the tutor said the material didn't cover it.
"""

import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.main import app, lifespan
from app.models import Material, MessageSource, User
from app.models import Module as ModuleRow
from app.services.search.embedding import Embedder
from tests.api.conftest import ClientFactory
from tests.fakes import FakeEmbedder, FakeLLM, streamed
from tests.search.conftest import Page, add_material, run_jobs
from tests.tutor.conftest import CIPHER, FIREWALL, Module, sse_events

# A second deck on the same subject (it ranks among the first question's sources).
STATEFUL_NOTES = "Stateful inspection firewall notes: how a firewall tracks each connection."

FIRST = {"question": "How does a stateful inspection firewall work?"}


async def alice(client_as: ClientFactory, session: AsyncSession, module: Module) -> Any:
    user = await session.get(User, module.user_id)
    assert user is not None
    return client_as(user)


async def ask(api: httpx.AsyncClient, conversation_id: str, body: dict[str, Any]) -> list[Any]:
    response = await api.post(f"/conversations/{conversation_id}/messages", json=body)
    assert response.status_code == 200, response.text
    return sse_events(response.text)


def sources_of(events: list[Any]) -> list[tuple[str, str, int]]:
    return [(s["label"], s["material_title"], s["page_number"]) for s in events[0][1]["sources"]]


async def conversation(api: httpx.AsyncClient, module: Module) -> str:
    response = await api.post(f"/modules/{module.module_id}/tutor/conversations", json={})
    assert response.status_code == 201
    return str(response.json()["id"])


# --- the follow-up modes reuse the last answer's sources ---


@pytest.mark.parametrize("mode", ["explain_differently", "example"])
async def test_a_follow_up_mode_is_given_the_last_answers_sources_again(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
    mode: str,
) -> None:
    fake_llm.reply(
        "flash", streamed("It tracks connections [S1]."), streamed("Like a doorman [S1].")
    )
    async with await alice(client_as, session, module) as api:
        conversation_id = await conversation(api, module)
        first = await ask(api, conversation_id, FIRST)
        again = await ask(
            api,
            conversation_id,
            {"question": "Explain that differently, as if to a first-year student", "mode": mode},
        )
        stored = (await api.get(f"/conversations/{conversation_id}")).json()["messages"]

    assert sources_of(again) == sources_of(first)
    assert sources_of(first)[0] == ("S1", "CH09", 1)
    assert again[-1][1]["cited"] == ["S1"]
    # The very same passages, labels and chunks.
    assert [(s["label"], s["page_number"]) for s in stored[3]["sources"]] == [
        (s["label"], s["page_number"]) for s in stored[1]["sources"]
    ]
    chunk_ids = list(
        await session.scalars(
            select(MessageSource.chunk_id)
            .where(
                MessageSource.message_id.in_(
                    [uuid.UUID(stored[1]["id"]), uuid.UUID(stored[3]["id"])]
                )
            )
            .order_by(MessageSource.message_id, MessageSource.rank)
        )
    )
    assert None not in chunk_ids and len(set(chunk_ids)) == len(chunk_ids) // 2
    assert FIREWALL[:40] in fake_llm.requests[-1].body["messages"][-1]["content"]


async def test_a_follow_up_mode_with_no_earlier_answer_searches(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
) -> None:
    fake_llm.reply("flash", streamed("Ciphers use a key [S1]."))
    async with await alice(client_as, session, module) as api:
        conversation_id = await conversation(api, module)
        events = await ask(
            api,
            conversation_id,
            {"question": "Give an example of AES symmetric ciphers", "mode": "example"},
        )

    assert sources_of(events)[0][1:] == ("CH09", 3)


async def test_a_reused_source_whose_chunk_is_gone_comes_back_from_its_page(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
) -> None:
    fake_llm.reply("flash", streamed("Tracked [S1]."), streamed("Again [S1]."))
    async with await alice(client_as, session, module) as api:
        conversation_id = await conversation(api, module)
        first = sources_of(await ask(api, conversation_id, FIRST))
        # A re-index replaced S1's chunk: its link is gone (set to null by the FK).
        await session.execute(
            update(MessageSource).where(MessageSource.label == "S1").values(chunk_id=None)
        )
        await session.commit()
        again = sources_of(
            await ask(
                api, conversation_id, {"question": "Give me an example of that.", "mode": "example"}
            )
        )

    assert again == first
    assert FIREWALL[:40] in fake_llm.requests[-1].body["messages"][-1]["content"]


async def test_turning_ai_off_drops_a_reused_source_and_the_others_keep_their_labels(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
    tmp_path: Path,
) -> None:
    user = await session.get(User, module.user_id)
    rows_module = await session.get(ModuleRow, module.module_id)
    assert user is not None and rows_module is not None
    await add_material(session, user, rows_module, "CH10", [Page(STATEFUL_NOTES)])
    await run_jobs(session, tmp_path)
    fake_llm.reply("flash", streamed("Tracked [S1][S2]."), streamed("Again."))
    async with await alice(client_as, session, module) as api:
        conversation_id = await conversation(api, module)
        asked = await ask(api, conversation_id, FIRST)
        first = sources_of(asked)
        # Turn AI off for the material at S1.
        s1 = asked[0][1]["sources"][0]
        material = await session.get(Material, uuid.UUID(s1["material_id"]))
        assert material is not None
        material.allow_ai = False
        await session.commit()
        events = await ask(
            api, conversation_id, {"question": "Give me an example of that.", "mode": "example"}
        )
        stored = (await api.get(f"/conversations/{conversation_id}")).json()["messages"][3]

    again = sources_of(events)
    assert {title for _, title, _ in first} == {"CH09", "CH10"}
    # The other material is left, under the labels it had (not renumbered from S1).
    assert again == [source for source in first if source[1] != s1["material_title"]]
    assert again and again[0][0] != "S1"
    assert [(s["label"], s["rank"]) for s in stored["sources"]] == [
        (label, int(label[1:])) for label, *_ in again
    ]
    sent = fake_llm.requests[-1].body["messages"][-1]["content"]
    assert f'title="{s1["material_title"]}"' not in sent


# --- a new question in a conversation searches with the previous one as context ---


async def test_a_short_follow_up_keeps_its_context(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
    fake_embedder: FakeEmbedder,
) -> None:
    fake_llm.reply("flash", streamed("It tracks [S1]."), streamed("Yes [S1]."))
    async with await alice(client_as, session, module) as api:
        conversation_id = await conversation(api, module)
        await ask(api, conversation_id, FIRST)
        fake_embedder.query_calls.clear()
        events = await ask(api, conversation_id, {"question": "Why does that matter?"})

    # Two searches: the follow-up, then the previous question and the follow-up together.
    assert fake_embedder.query_calls == [
        "Why does that matter?",
        "How does a stateful inspection firewall work? Why does that matter?",
    ]
    assert sources_of(events)[0] == ("S1", "CH09", 1)


async def test_a_change_of_subject_still_finds_its_own_pages(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
) -> None:
    fake_llm.reply("flash", streamed("It tracks [S1]."), streamed("One key [S1]."))
    async with await alice(client_as, session, module) as api:
        conversation_id = await conversation(api, module)
        await ask(api, conversation_id, FIRST)
        events = await ask(
            api, conversation_id, {"question": "What do symmetric ciphers such as AES use?"}
        )

    assert sources_of(events)[0] == ("S1", "CH09", 3)
    assert CIPHER[:30] in fake_llm.requests[-1].body["messages"][-1]["content"]


async def test_the_first_question_searches_once(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
    fake_embedder: FakeEmbedder,
) -> None:
    fake_llm.reply("flash", streamed("It tracks [S1]."))
    fake_embedder.query_calls.clear()
    async with await alice(client_as, session, module) as api:
        await ask(api, await conversation(api, module), FIRST)

    assert fake_embedder.query_calls == [FIRST["question"]]


# --- a session's conversation, found again after a reload ---


async def test_a_sessions_conversation_is_listed_for_that_session(
    client_as: ClientFactory, session: AsyncSession, module: Module, user_b: User
) -> None:
    async with await alice(client_as, session, module) as api:
        older = (
            await api.post(
                f"/modules/{module.module_id}/tutor/conversations",
                json={"study_session_id": str(module.study_id)},
            )
        ).json()
        other = await conversation(api, module)  # no session
        listed = await api.get(
            f"/modules/{module.module_id}/tutor/conversations",
            params={"study_session_id": str(module.study_id)},
        )
        everything = await api.get(f"/modules/{module.module_id}/tutor/conversations")
        missing = await api.get(
            f"/modules/{module.module_id}/tutor/conversations",
            params={"study_session_id": str(uuid.uuid4())},
        )

    assert listed.status_code == 200
    assert [c["id"] for c in listed.json()] == [older["id"]]
    assert listed.json()[0]["messages"] == []
    assert {c["id"] for c in everything.json()} == {older["id"], other}
    assert missing.json() == []


async def test_another_users_session_id_lists_nothing_in_your_own_module(
    client_as: ClientFactory, session: AsyncSession, module: Module, user_b: User
) -> None:
    """Bob filters his own module by Alice's session: [] exactly like a missing ID."""
    from tests.academics.conftest import make_rows

    bob = await make_rows(session, user_b)
    bob_module = bob.module.id
    async with await alice(client_as, session, module) as api:
        await api.post(
            f"/modules/{module.module_id}/tutor/conversations",
            json={"study_session_id": str(module.study_id)},
        )
    async with client_as(user_b) as api:
        listed = await api.get(
            f"/modules/{bob_module}/tutor/conversations",
            params={"study_session_id": str(module.study_id)},
        )

    assert (listed.status_code, listed.json()) == (200, [])


# --- the embedding model loads at startup ---


async def test_the_api_loads_the_embedding_model_as_it_starts(
    fake_embedder: FakeEmbedder,
) -> None:
    async with lifespan(app):
        loaded: Embedder = await app.state.embedder_loading

    assert loaded is fake_embedder


async def test_preloading_can_be_turned_off(monkeypatch: pytest.MonkeyPatch) -> None:
    off = get_settings().model_copy(update={"preload_embedder": False})
    monkeypatch.setattr("app.main.get_settings", lambda: off)
    if hasattr(app.state, "embedder_loading"):
        del app.state.embedder_loading

    async with lifespan(app):
        assert not hasattr(app.state, "embedder_loading")
