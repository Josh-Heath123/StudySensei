"""The consistency check (ADR 0030): after generating, one batched call judges each short
answer's reference answer against its own key points, with the marking judgement. Code removes
uncovered key points and drops an item left with none, counted as key_points_not_in_answer."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LLMClient
from app.jobs.worker import run_once
from app.models import PracticeGeneration, PracticeItem, User
from app.schemas.practice import GeneratedItem, consistency_reply
from app.services.practice.generation import (
    CHECK_SYSTEM,
    UNCHECKED,
    apply_check,
    check_messages,
    request_generation,
)
from app.services.practice.marking import COVERAGE_RULES, MARKING_SYSTEM
from app.services.practice.prompts import PRACTICE_SYSTEM
from app.storage.local import LocalStorage
from tests.fakes import FakeLLM, ok
from tests.practice.conftest import Practice, card, checked, generated, question

FIRST = question(
    "How does a stateful firewall differ from a packet filter?",
    "It tracks connections; a packet filter checks each packet on its own.",
    ["Tracks connections", "Logs every dropped packet", "Packet filters judge alone"],
    ["S1", "S2"],
)
SECOND = question(
    "Why does a proxy firewall see the protocol?",
    "It relays the traffic itself.",
    ["Runs on a dedicated host"],
    ["S3"],
)
REPLY = generated(
    card("What does a state table let a firewall do?", "Allow replies to seen ones.", ["S1"]),
    FIRST,
    SECOND,
)


async def run_worker(session: AsyncSession, tmp_path: Path) -> None:
    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        yield session

    storage = LocalStorage(tmp_path)
    while await run_once(sessions, storage):
        pass


def items_of(*raw: dict[str, object]) -> list[GeneratedItem]:
    return [GeneratedItem.model_validate(r) for r in raw]


def test_the_prompt_says_key_points_summarise_the_reference_answer() -> None:
    assert "The reference answer must state every key point." in PRACTICE_SYSTEM
    assert "Key points summarise the" in PRACTICE_SYSTEM
    assert "reference answer and add nothing to it." in PRACTICE_SYSTEM


def test_the_check_uses_the_marking_judgement() -> None:
    assert COVERAGE_RULES.format(answer="item's reference answer") in CHECK_SYSTEM
    assert COVERAGE_RULES.format(answer="student's answer") in MARKING_SYSTEM


def test_the_check_numbers_each_short_answer_and_its_key_points() -> None:
    first, second = items_of(FIRST, SECOND)
    sent = check_messages([first, second])[1].text
    assert "Item 1\nQuestion: How does a stateful firewall" in sent
    assert "Reference answer: It tracks connections;" in sent
    assert "  2. Logs every dropped packet" in sent
    assert "Item 2\n" in sent and "  1. Runs on a dedicated host" in sent
    assert "For each of the 2 items" in sent


def test_code_removes_uncovered_points_and_drops_an_item_left_with_none() -> None:
    flash = card("What is a state table?", "A list.", ["S1"])
    flash_item, first, second = items_of(flash, FIRST, SECOND)
    reply = consistency_reply([3, 1]).model_validate_json(checked([True, False, True], [False]))
    found = apply_check([flash_item, first, second], [first, second], reply)
    kept = found.items
    assert (found.dropped, found.removed) == (1, 1)
    assert [i.prompt for i in kept] == [flash_item.prompt, first.prompt]
    assert kept[1].key_points == ["Tracks connections", "Packet filters judge alone"]
    # The input isn't changed.
    assert first.key_points is not None and len(first.key_points) == 3


def test_the_reply_must_cover_every_item_and_key_point_once() -> None:
    schema = consistency_reply([2, 1])
    schema.model_validate_json(checked([True, True], [False]))
    for bad in (
        checked([True, True]),  # item 2 missing
        checked([True], [False]),  # item 1's second key point missing
        checked([True, True], [False, True]),  # item 2 has one key point
        checked([True, True], [False], [True]),  # an item too many
    ):
        with pytest.raises(ValidationError):
            schema.model_validate_json(bad)
    with pytest.raises(ValueError):
        consistency_reply([])
    with pytest.raises(ValueError):
        consistency_reply([6])


async def test_the_job_keeps_stated_points_and_counts_the_drop(
    session: AsyncSession,
    practice: Practice,
    practice_llm: LLMClient,
    fake_llm: FakeLLM,
    user_a: User,
    tmp_path: Path,
) -> None:
    email, name = user_a.email, user_a.display_name
    fake_llm.reply("flash", ok(REPLY), ok(checked([True, False, True], [False])))
    generation = await request_generation(session, practice.chapter, 8, user_id=practice.user_id)
    generation_id = generation.id
    await run_worker(session, tmp_path)

    done = await session.get(PracticeGeneration, generation_id, populate_existing=True)
    assert done is not None
    assert (done.status, done.produced) == ("succeeded", 2)
    assert done.dropped == {"key_points_not_in_answer": 1}
    stored = {
        i.prompt: i
        for i in await session.scalars(
            select(PracticeItem).where(PracticeItem.generation_id == generation_id)
        )
    }
    assert stored[FIRST["prompt"]].key_points == [
        "Tracks connections",
        "Packet filters judge alone",
    ]
    assert SECOND["prompt"] not in stored

    # Two calls: the items, then one batched check of both short answers (not the card).
    assert len(fake_llm.requests) == 2
    check = fake_llm.requests[1].body
    sent = json.dumps(check["messages"])
    assert "Item 2" in sent and "Item 3" not in sent and "state table let" not in sent
    for private in (email, name):
        assert private not in sent


async def test_a_check_that_fails_fails_the_generation_readably(
    session: AsyncSession,
    practice: Practice,
    practice_llm: LLMClient,
    fake_llm: FakeLLM,
    tmp_path: Path,
) -> None:
    # The check's reply misses an item, and so does its repair.
    fake_llm.reply("flash", ok(REPLY), ok(checked([True, True, True])), ok("not json"))
    generation = await request_generation(session, practice.chapter, 8, user_id=practice.user_id)
    generation_id = generation.id
    await run_worker(session, tmp_path)

    failed = await session.get(PracticeGeneration, generation_id, populate_existing=True)
    assert failed is not None
    assert (failed.status, failed.error, failed.produced) == ("failed", UNCHECKED, 0)
    assert await session.scalar(select(PracticeItem.id).limit(1)) is None


async def test_a_batch_of_flashcards_needs_no_check(
    session: AsyncSession,
    practice: Practice,
    practice_llm: LLMClient,
    fake_llm: FakeLLM,
    tmp_path: Path,
) -> None:
    fake_llm.reply("flash", ok(generated(card("What is a state table?", "A list.", ["S1"]))))
    generation = await request_generation(session, practice.chapter, 4, user_id=practice.user_id)
    generation_id = generation.id
    await run_worker(session, tmp_path)

    done = await session.get(PracticeGeneration, generation_id, populate_existing=True)
    assert done is not None and (done.status, done.produced, done.dropped) == ("succeeded", 1, {})
    assert len(fake_llm.requests) == 1
