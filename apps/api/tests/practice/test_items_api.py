"""Practice items over HTTP (ADR 0025): generating, listing with sources, the student's own
items, edits (an AI item edited becomes the student's), rejecting, deleting, reviews (append
only), and what topic merges, topic deletes and material deletes do to items."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LLMClient
from app.jobs.worker import run_once
from app.models import Material, Review, User
from app.storage.local import LocalStorage
from tests.api.conftest import ClientFactory
from tests.fakes import FakeLLM, ok
from tests.practice.conftest import Practice, card, generated, question

LATER = datetime.now(UTC) + timedelta(hours=1)


@pytest.fixture
async def api(client_as: ClientFactory, user_a: User) -> AsyncIterator[AsyncClient]:
    async with client_as(user_a) as client:
        yield client


async def run_worker(session: AsyncSession, tmp_path: Path) -> None:
    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        yield session

    for _ in range(5):
        if not await run_once(sessions, LocalStorage(tmp_path / "s"), now=lambda: LATER):
            return


async def generate(
    api: AsyncClient, session: AsyncSession, fake_llm: FakeLLM, tmp_path: Path, topic: uuid.UUID
) -> list[dict[str, Any]]:
    fake_llm.reply(
        "flash",
        ok(
            generated(
                card("What does a state table hold?", "Connections already seen.", ["S1"]),
                question(
                    "How does a proxy firewall differ from a packet filter?",
                    "It relays traffic and inspects the protocol.",
                    ["Relays traffic", "Inspects the protocol"],
                    ["S2", "S3"],
                ),
            )
        ),
    )
    response = await api.post(f"/topics/{topic}/practice/generate", json={"count": 4})
    assert response.status_code == 202, response.text
    body = response.json()
    assert (body["status"], body["requested"], body["topic_id"]) == ("queued", 4, str(topic))
    await run_worker(session, tmp_path)
    listed = await api.get("/practice/items", params={"topic_id": str(topic)})
    return list(listed.json()["items"])


async def test_generate_then_list_with_sources(
    api: AsyncClient,
    session: AsyncSession,
    practice: Practice,
    practice_llm: LLMClient,
    fake_llm: FakeLLM,
    tmp_path: Path,
) -> None:
    found = await generate(api, session, fake_llm, tmp_path, practice.chapter)
    by_prompt = {i["prompt"]: i for i in found}
    proxy = by_prompt["How does a proxy firewall differ from a packet filter?"]
    assert proxy["origin"] == "ai" and proxy["sources_missing"] is False
    assert proxy["key_points"] == ["Relays traffic", "Inspects the protocol"]
    assert proxy["sources"] == [
        {
            "label": "S2",
            "material_id": str(practice.materials["slides"]),
            "material_title": "CH09 Firewalls",
            "page_number": 2,
        },
        {
            "label": "S3",
            "material_id": str(practice.materials["slides"]),
            "material_title": "CH09 Firewalls",
            "page_number": 3,
        },
    ]
    generations = (await api.get(f"/topics/{practice.chapter}/practice/generations")).json()
    assert [(g["status"], g["produced"], g["dropped"]) for g in generations] == [
        ("succeeded", 2, {})
    ]
    # Filters.
    page = (await api.get("/practice/items", params={"origin": "user"})).json()
    assert page == {"items": [], "total": 0}
    page = (await api.get("/practice/items", params={"limit": 1})).json()
    assert len(page["items"]) == 1 and page["total"] == 2


async def test_generate_errors(api: AsyncClient, practice: Practice) -> None:
    empty = (
        await api.post(f"/modules/{practice.module_id}/topics", json={"name": "Nothing linked"})
    ).json()
    refused = await api.post(f"/topics/{empty['id']}/practice/generate")
    assert refused.status_code == 422
    assert refused.json()["detail"] == "No AI-allowed slides or notes are linked to this topic."
    assert (await api.post(f"/topics/{practice.chapter}/practice/generate")).status_code == 202
    again = await api.post(f"/topics/{practice.chapter}/practice/generate", json={"count": 6})
    assert again.status_code == 409
    for count in (3, 13):
        bad = await api.post(f"/topics/{practice.sub}/practice/generate", json={"count": count})
        assert bad.status_code == 422


async def test_own_items_edits_rejects_and_deletes(
    api: AsyncClient,
    session: AsyncSession,
    practice: Practice,
    practice_llm: LLMClient,
    fake_llm: FakeLLM,
    tmp_path: Path,
) -> None:
    mine = await api.post(
        "/practice/items",
        json={
            "module_id": str(practice.module_id),
            "topic_id": str(practice.sub),
            "kind": "short_answer",
            "prompt": "Why keep a state table?",
            "answer": "To allow replies.",
            "key_points": ["Replies"],
        },
    )
    assert mine.status_code == 201, mine.text
    assert (mine.json()["origin"], mine.json()["sources"]) == ("user", [])
    # The same prompt in the same topic is a conflict; key points must fit the kind.
    same = {**mine.json(), "module_id": str(practice.module_id), "topic_id": str(practice.sub)}
    body = {k: same[k] for k in ("module_id", "topic_id", "kind", "prompt", "answer", "key_points")}
    assert (await api.post("/practice/items", json=body)).status_code == 409
    no_points = {**body, "prompt": "Another one?", "key_points": None}
    assert (await api.post("/practice/items", json=no_points)).status_code == 422
    flash_points = {**body, "kind": "flashcard", "prompt": "Another one?"}
    assert (await api.post("/practice/items", json=flash_points)).status_code == 422

    [ai_card, _] = sorted(
        await generate(api, session, fake_llm, tmp_path, practice.chapter),
        key=lambda i: i["kind"],
    )
    item_id = ai_card["id"]
    # Moving it or suspending it keeps it the AI's; editing its text makes it the student's.
    moved = await api.patch(
        f"/practice/items/{item_id}", json={"topic_id": str(practice.sub), "status": "suspended"}
    )
    assert (moved.json()["origin"], moved.json()["status"]) == ("ai", "suspended")
    edited = (await api.patch(f"/practice/items/{item_id}", json={"answer": "Mine now."})).json()
    assert (edited["origin"], edited["answer"]) == ("user", "Mine now.")
    assert [s["label"] for s in edited["sources"]] == ["S1"]  # its sources stay
    assert edited["provider"] == "gemini"

    # Rejecting needs a reason; un-rejecting clears it.
    assert (
        await api.patch(f"/practice/items/{item_id}", json={"status": "rejected"})
    ).status_code == 422
    rejected = await api.patch(
        f"/practice/items/{item_id}", json={"status": "rejected", "reject_reason": "unclear"}
    )
    assert (rejected.json()["status"], rejected.json()["reject_reason"]) == ("rejected", "unclear")
    back = (await api.patch(f"/practice/items/{item_id}", json={"status": "active"})).json()
    assert (back["status"], back["reject_reason"]) == ("active", None)
    assert (await api.patch(f"/practice/items/{item_id}", json={"prompt": None})).status_code == 422
    assert (
        await api.patch(f"/practice/items/{item_id}", json={"key_points": ["No"]})
    ).status_code == 422

    assert (await api.delete(f"/practice/items/{item_id}")).status_code == 204
    assert (await api.delete(f"/practice/items/{item_id}")).status_code == 404


async def test_reviews_are_append_only(
    api: AsyncClient, session: AsyncSession, practice: Practice
) -> None:
    item = (
        await api.post(
            "/practice/items",
            json={
                "module_id": str(practice.module_id),
                "kind": "flashcard",
                "prompt": "What is a packet filter?",
                "answer": "A rule check on each packet.",
            },
        )
    ).json()
    first = await api.post(f"/practice/items/{item['id']}/reviews", json={"grade": 1})
    assert first.status_code == 201
    review = first.json()["review"]
    assert (review["marked_by"], review["grade"], review["fsrs_version"]) == (
        "self",
        1,
        "fsrs 6.3.3",
    )
    second = await api.post(
        f"/practice/items/{item['id']}/reviews",
        json={"grade": 3, "duration_ms": 4200, "answer_text": "Checks rules per packet."},
    )
    assert second.status_code == 201
    for bad in ({"grade": 0}, {"grade": 5}, {"grade": 3, "answer_text": "x" * 2001}):
        assert (
            await api.post(f"/practice/items/{item['id']}/reviews", json=bad)
        ).status_code == 422
    listed = (await api.get(f"/practice/items/{item['id']}/reviews")).json()
    assert [r["grade"] for r in listed] == [3, 1]  # newest first
    assert listed[0]["duration_ms"] == 4200

    # Postgres refuses to change a review.
    with pytest.raises(DBAPIError, match="append-only"):
        await session.execute(update(Review).values(grade=4))
    await session.rollback()
    # But a review still goes with its item.
    assert (await api.delete(f"/practice/items/{item['id']}")).status_code == 204
    assert await session.scalar(select(Review.id).limit(1)) is None


async def test_a_rejected_or_suspended_item_cant_be_reviewed(
    api: AsyncClient, practice: Practice
) -> None:
    item = (
        await api.post(
            "/practice/items",
            json={
                "module_id": str(practice.module_id),
                "kind": "flashcard",
                "prompt": "What is a packet filter?",
                "answer": "A rule check on each packet.",
            },
        )
    ).json()
    await api.patch(
        f"/practice/items/{item['id']}", json={"status": "rejected", "reject_reason": "wrong"}
    )
    refused = await api.post(f"/practice/items/{item['id']}/reviews", json={"grade": 3})
    assert refused.status_code == 409
    assert refused.json()["detail"] == "Restore it before reviewing."
    await api.patch(f"/practice/items/{item['id']}", json={"status": "suspended"})
    suspended = await api.post(f"/practice/items/{item['id']}/reviews", json={"grade": 3})
    assert (suspended.status_code, suspended.json()["detail"]) == (
        409,
        "Restore it before reviewing.",
    )
    await api.patch(f"/practice/items/{item['id']}", json={"status": "active"})
    assert (
        await api.post(f"/practice/items/{item['id']}/reviews", json={"grade": 3})
    ).status_code == 201


async def own(api: AsyncClient, practice: Practice, topic: uuid.UUID, prompt: str) -> str:
    response = await api.post(
        "/practice/items",
        json={
            "module_id": str(practice.module_id),
            "topic_id": str(topic),
            "kind": "flashcard",
            "prompt": prompt,
            "answer": "An answer.",
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def test_a_merge_moves_items_and_rejects_duplicates(
    api: AsyncClient, practice: Practice
) -> None:
    kept = await own(api, practice, practice.other, "What is a symmetric cipher?")
    duplicate = await own(api, practice, practice.other, "What is a packet filter?")
    await own(api, practice, practice.chapter, "what is a  PACKET filter?")
    merged = await api.post(
        f"/topics/{practice.other}/merge-into", json={"target_id": str(practice.chapter)}
    )
    assert merged.status_code == 200, merged.text
    items = {
        i["id"]: i
        for i in (
            await api.get("/practice/items", params={"topic_id": str(practice.chapter)})
        ).json()["items"]
    }
    assert items[kept]["status"] == "active"
    assert (items[duplicate]["status"], items[duplicate]["reject_reason"]) == (
        "rejected",
        "duplicate",
    )
    assert len(items) == 3


async def test_a_topic_delete_keeps_its_items_without_a_topic(
    api: AsyncClient, practice: Practice
) -> None:
    on_sub = await own(api, practice, practice.sub, "What is a packet filter?")
    # Same prompt, no topic: topicless items don't clash.
    await own_without_topic(api, practice, "What is a packet filter?")
    assert (await api.delete(f"/topics/{practice.chapter}")).status_code == 204  # and its sub
    items = (await api.get("/practice/items", params={"module_id": str(practice.module_id)})).json()
    found = {i["id"]: i for i in items["items"]}
    assert found[on_sub]["topic_id"] is None
    assert items["total"] == 2


async def own_without_topic(api: AsyncClient, practice: Practice, prompt: str) -> None:
    response = await api.post(
        "/practice/items",
        json={
            "module_id": str(practice.module_id),
            "kind": "flashcard",
            "prompt": prompt,
            "answer": "An answer.",
        },
    )
    assert response.status_code == 201


async def test_deleting_the_material_leaves_sources_missing(
    api: AsyncClient,
    session: AsyncSession,
    practice: Practice,
    practice_llm: LLMClient,
    fake_llm: FakeLLM,
    tmp_path: Path,
) -> None:
    await generate(api, session, fake_llm, tmp_path, practice.chapter)
    material = await session.get(Material, practice.materials["slides"])
    assert material is not None
    await session.delete(material)
    await session.commit()
    found = (await api.get("/practice/items")).json()["items"]
    assert found and all(i["sources"] == [] and i["sources_missing"] for i in found)
    # The student's own never had sources: nothing is missing.
    await own(api, practice, practice.sub, "What is a packet filter?")
    mine = (await api.get("/practice/items", params={"origin": "user"})).json()["items"]
    assert [i["sources_missing"] for i in mine] == [False]


async def test_an_omitted_body_generates_eight(api: AsyncClient, practice: Practice) -> None:
    response = await api.post(f"/topics/{practice.chapter}/practice/generate")
    assert response.json()["requested"] == 8


async def test_two_passages_of_one_page_are_one_page(
    api: AsyncClient, session: AsyncSession, practice: Practice
) -> None:
    """Post-merge review of #48: an item citing two chunks of p1 showed "p1; p1"."""
    from app.models import Chunk, PracticeItemSource

    second = Chunk(
        id=uuid.uuid4(),
        user_id=practice.user_id,
        module_id=practice.module_id,
        material_id=practice.materials["slides"],
        page_number=1,
        position=1,
        text="More on state tables.",
        token_count=4,
        embedding=[1.0] + [0.0] * 383,
    )
    session.add(second)
    await session.commit()
    item_id = await own(api, practice, practice.chapter, "What does a state table hold?")
    session.add_all(
        PracticeItemSource(
            item_id=uuid.UUID(item_id), chunk_id=chunk, user_id=practice.user_id, label=label
        )
        for label, chunk in (
            ("S1", practice.chunks["FIREWALL"]),
            ("S2", practice.chunks["FILTER"]),
            ("S3", second.id),
        )
    )
    await session.commit()
    [item] = (await api.get("/practice/items")).json()["items"]
    assert [(s["label"], s["page_number"]) for s in item["sources"]] == [
        ("S1", 1),
        ("S2", 2),
        ("S3", 1),
    ]
    slides = str(practice.materials["slides"])
    assert item["pages"] == [
        {"material_id": slides, "material_title": "CH09 Firewalls", "page_number": 1},
        {"material_id": slides, "material_title": "CH09 Firewalls", "page_number": 2},
    ]


async def test_items_can_be_listed_by_kind(api: AsyncClient, practice: Practice) -> None:
    base = {"module_id": str(practice.module_id), "topic_id": str(practice.chapter)}
    await api.post(
        "/practice/items",
        json={**base, "kind": "flashcard", "prompt": "AES?", "answer": "A cipher."},
    )
    await api.post(
        "/practice/items",
        json={
            **base,
            "kind": "short_answer",
            "prompt": "Why use a salt?",
            "answer": "So equal passwords hash differently.",
            "key_points": ["Equal passwords hash differently"],
        },
    )
    for kind in ("flashcard", "short_answer"):
        listed = (await api.get("/practice/items", params={"kind": kind})).json()
        assert [i["kind"] for i in listed["items"]] == [kind] and listed["total"] == 1
    assert (await api.get("/practice/items", params={"kind": "essay"})).status_code == 422


async def test_a_topics_items_can_include_its_subtopics(
    api: AsyncClient, practice: Practice
) -> None:
    for topic, prompt in ((practice.chapter, "Chapter?"), (practice.sub, "Sub?")):
        created = await api.post(
            "/practice/items",
            json={
                "module_id": str(practice.module_id),
                "topic_id": str(topic),
                "kind": "flashcard",
                "prompt": prompt,
                "answer": "Yes.",
            },
        )
        assert created.status_code == 201, created.text
    chapter = {"topic_id": str(practice.chapter)}
    only = (await api.get("/practice/items", params=chapter)).json()
    both = (await api.get("/practice/items", params={**chapter, "subtopics": "true"})).json()
    assert [i["prompt"] for i in only["items"]] == ["Chapter?"]
    assert sorted(i["prompt"] for i in both["items"]) == ["Chapter?", "Sub?"]
    assert both["total"] == 2
    sub = {"topic_id": str(practice.sub), "subtopics": "true"}
    assert (await api.get("/practice/items", params=sub)).json()["total"] == 1
