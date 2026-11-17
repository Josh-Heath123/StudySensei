"""Long materials in parts, cut-off replies, and the per-material call cap (ADR 0007)."""

import functools
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LLMClient
from app.ai.sources import SourcePage
from app.jobs.worker import run_once
from app.models import AIUsage, Job, Material, TopicProposal, User
from app.models import Module as ModuleRow
from app.services.topic_maps import queue_extraction
from app.services.topic_maps.prompts import plan_parts
from app.storage.local import LocalStorage
from tests.fakes import FakeLLM, ok, overloaded
from tests.search.conftest import Page, add_material, run_jobs
from tests.topic_maps.conftest import LITE, Module, node, topics_reply
from tests.topic_maps.extraction_helpers import proposal_of


async def a_long_material(
    session: AsyncSession,
    module: Module,
    tmp_path: Path,
    fake_llm: FakeLLM,
    pages: int,
    title: str = "Textbook",
) -> uuid.UUID:
    """An indexed notes file of ``pages`` pages, with no jobs left and no requests recorded."""
    user = await session.get(User, module.user_id)
    row = await session.get(ModuleRow, module.module_id)
    assert user is not None and row is not None
    material = await add_material(
        session,
        user,
        row,
        title,
        [Page(f"Page {n} explains topic {n}.") for n in range(1, pages + 1)],
    )
    material.kind = "notes"
    await session.commit()
    material_id = material.id
    await run_jobs(session, tmp_path)
    await session.execute(delete(Job).where(Job.user_id == module.user_id))
    await session.commit()
    # Indexing queued an extraction that ran (and failed) with nothing scripted: forget it.
    fake_llm.requests.clear()
    return material_id


async def queue_for(session: AsyncSession, material_id: uuid.UUID) -> uuid.UUID:
    material = await session.get(Material, material_id, populate_existing=True)
    assert material is not None
    job = queue_extraction(session, material)
    await session.commit()
    return job.id


async def run_with_retries(session: AsyncSession, tmp_path: Path, rounds: int = 5) -> None:
    """Run the worker repeatedly, an hour later each time, so backed-off retries come due."""

    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        yield session

    storage = LocalStorage(tmp_path / "storage")
    for hours in range(1, rounds + 1):
        clock = functools.partial(lambda at: at, datetime.now(UTC) + timedelta(hours=hours))
        while await run_once(sessions, storage, now=clock):
            pass


def prompt_of(request_body: dict[str, object]) -> str:
    messages = request_body["messages"]
    assert isinstance(messages, list)
    return str(messages[-1]["content"])


def test_parts_are_even_and_capped() -> None:
    pages = [SourcePage(n, None, "x") for n in range(1, 91)]

    assert [len(p) for p in plan_parts(pages, part_pages=40, max_parts=3)] == [30, 30, 30]
    assert [len(p) for p in plan_parts(pages[:40], part_pages=40, max_parts=3)] == [40]
    # Very long: bigger parts rather than more calls.
    many = [SourcePage(n, None, "x") for n in range(1, 301)]
    assert [len(p) for p in plan_parts(many, part_pages=40, max_parts=3)] == [100, 100, 100]


async def test_a_long_material_is_analysed_in_parts_and_combined(
    session: AsyncSession, module: Module, client: LLMClient, fake_llm: FakeLLM, tmp_path: Path
) -> None:
    material_id = await a_long_material(session, module, tmp_path, fake_llm, pages=90)
    fake_llm.reply(
        LITE,
        topics_reply(node("Cryptography", [1, 2], subtopics=[node("Ciphers", [3])])),
        topics_reply(
            node("cryptography", [31], subtopics=[node("Hashes", [40])]), node("Keys", [50])
        ),
        topics_reply(node("Firewalls", [61])),
        ok('{"topics": []}'),  # the merge
    )
    await queue_for(session, material_id)

    await run_jobs(session, tmp_path)

    prompts = [prompt_of(r.body) for r in fake_llm.requests[:3]]
    assert "part 1 of 3: pages 1 to 30" in prompts[0]
    assert "part 3 of 3: pages 61 to 90" in prompts[2]
    assert "[page 31]" in prompts[1] and "[page 30]" not in prompts[1]
    saved = await proposal_of(session, material_id)
    assert [t["name"] for t in saved["topics"]] == ["Cryptography", "Keys", "Firewalls"]
    crypto = saved["topics"][0]
    assert crypto["pages"] == [1, 2, 31]
    assert [s["name"] for s in crypto["subtopics"]] == ["Ciphers", "Hashes"]


async def test_finished_parts_are_saved_and_not_paid_for_again(
    session: AsyncSession, module: Module, client: LLMClient, fake_llm: FakeLLM, tmp_path: Path
) -> None:
    material_id = await a_long_material(session, module, tmp_path, fake_llm, pages=90)
    fake_llm.reply(
        LITE,
        topics_reply(node("Cryptography", [1])),
        httpx.Response(400, json={"error": {"message": "Bad request."}}),
    )
    job_id = await queue_for(session, material_id)

    await run_jobs(session, tmp_path)

    failed = await session.get(Job, job_id, populate_existing=True)
    assert failed is not None and failed.status == "failed"
    assert failed.last_error is not None and "gemini: HTTP 400: Bad request." in failed.last_error
    assert list(failed.payload["parts"]) == ["1-30"]

    # The same job, run again (as a reschedule would): only parts 2 and 3 are asked for.
    failed.status, failed.attempts, failed.finished_at = "queued", 0, None
    await session.commit()
    before = len(fake_llm.requests)
    fake_llm.reply(LITE, topics_reply(node("Keys", [31])), topics_reply(node("Firewalls", [61])))
    fake_llm.reply(LITE, ok('{"topics": []}'))

    await run_jobs(session, tmp_path)

    asked = [prompt_of(r.body) for r in fake_llm.requests[before:]]
    assert "part 2 of 3" in asked[0] and "part 3 of 3" in asked[1]
    saved = await proposal_of(session, material_id)
    assert [t["name"] for t in saved["topics"]] == ["Cryptography", "Keys", "Firewalls"]


async def test_a_cut_off_reply_splits_the_part_in_half(
    session: AsyncSession, module: Module, client: LLMClient, fake_llm: FakeLLM, tmp_path: Path
) -> None:
    material_id = await a_long_material(session, module, tmp_path, fake_llm, pages=10)
    fake_llm.reply(
        LITE,
        ok('{"topics": [{"name": "Crypt', finish_reason="length"),
        topics_reply(node("Cryptography", [1])),
        topics_reply(node("Firewalls", [6])),
        ok('{"topics": []}'),
    )
    await queue_for(session, material_id)

    await run_jobs(session, tmp_path)

    asked = [prompt_of(r.body) for r in fake_llm.requests[:3]]
    assert "[page 10]" in asked[0]
    assert "[page 5]" in asked[1] and "[page 6]" not in asked[1]
    assert "[page 6]" in asked[2]
    saved = await proposal_of(session, material_id)
    assert [t["name"] for t in saved["topics"]] == ["Cryptography", "Firewalls"]


async def test_a_cut_off_reply_for_a_tiny_part_fails_plainly(
    session: AsyncSession, module: Module, client: LLMClient, fake_llm: FakeLLM, tmp_path: Path
) -> None:
    material_id = await a_long_material(session, module, tmp_path, fake_llm, pages=3)
    fake_llm.reply(LITE, ok("{", finish_reason="length"))
    job_id = await queue_for(session, material_id)

    await run_jobs(session, tmp_path)

    job = await session.get(Job, job_id, populate_existing=True)
    assert job is not None and job.status == "failed"
    assert job.last_error is not None and "cut off" in job.last_error
    assert len([r for r in fake_llm.requests if "topic map" not in prompt_of(r.body)]) == 1


async def test_at_most_four_calls_per_material_across_retries_and_no_cascade(
    session: AsyncSession, module: Module, client: LLMClient, fake_llm: FakeLLM, tmp_path: Path
) -> None:
    fake_llm.reply(LITE, *(ok("not json") for _ in range(10)))
    job_id = await queue_for(session, module.slides)

    await run_with_retries(session, tmp_path)

    job = await session.get(Job, job_id, populate_existing=True)
    assert job is not None and (job.status, job.attempts) == ("failed", 3)
    # Everything but the merge (whose prompt starts "Module:"), repairs included.
    extraction = [r for r in fake_llm.requests if not prompt_of(r.body).startswith("Module:")]
    assert len(extraction) == 4  # 2 (call + its repair), then 1, then 1: three attempts
    assert {r.model for r in fake_llm.requests} == {LITE}  # never Groq
    assert (
        await session.scalar(
            select(TopicProposal).where(TopicProposal.material_id == module.slides)
        )
        is None
    )


async def test_a_refused_request_fails_at_once_without_fallbacks(
    session: AsyncSession, module: Module, client: LLMClient, fake_llm: FakeLLM, tmp_path: Path
) -> None:
    fake_llm.reply(LITE, httpx.Response(400, json={"error": {"message": "Bad input."}}))
    job_id = await queue_for(session, module.slides)

    await run_jobs(session, tmp_path)

    job = await session.get(Job, job_id, populate_existing=True)
    assert job is not None and (job.status, job.attempts) == ("failed", 1)
    assert [r.model for r in fake_llm.requests] == [LITE]


# --- the COS330 failures after ADR 0007 (ADR 0008) ---


async def test_a_busy_model_doesnt_use_up_the_materials_calls(
    session: AsyncSession, module: Module, client: LLMClient, fake_llm: FakeLLM, tmp_path: Path
) -> None:
    """Chapter 7: four 503s in a row (two runs) used the whole cap. Now Groq answers."""
    fake_llm.reply(LITE, overloaded(), overloaded(), overloaded(), overloaded())
    fake_llm.reply("oss-120b", topics_reply(node("Firewalls", [1])), ok('{"topics": []}'))
    job_id = await queue_for(session, module.slides)

    await run_with_retries(session, tmp_path)

    job = await session.get(Job, job_id, populate_existing=True)
    assert job is not None and job.status == "succeeded"
    saved = await proposal_of(session, module.slides)
    assert [t["name"] for t in saved["topics"]] == ["Firewalls"]
    outcomes = await session.scalars(select(AIUsage.outcome).where(AIUsage.job_id == job_id))
    assert sorted(outcomes) == ["ok", "overloaded", "overloaded"]


async def test_names_under_title_need_no_repair(
    session: AsyncSession, module: Module, client: LLMClient, fake_llm: FakeLLM, tmp_path: Path
) -> None:
    """Chapters 1 and 5: every topic and subtopic came back without "name"."""
    fake_llm.reply(
        LITE,
        ok(
            json.dumps(
                {
                    "topics": [
                        {
                            "title": "Passwords",
                            "description": "Storing them.",
                            "pages": ["1"],
                            "subtopics": [{"title": "Hashing", "pages": "1"}],
                        }
                    ]
                }
            )
        ),
        ok('{"topics": []}'),
    )
    job_id = await queue_for(session, module.slides)

    await run_jobs(session, tmp_path)

    saved = await proposal_of(session, module.slides)
    assert saved["topics"][0]["name"] == "Passwords"
    assert saved["topics"][0]["subtopics"][0]["name"] == "Hashing"
    outcomes = await session.scalars(select(AIUsage.outcome).where(AIUsage.job_id == job_id))
    assert list(outcomes) == ["ok"]


async def test_a_reply_with_no_name_records_which_keys_it_had(
    session: AsyncSession, module: Module, client: LLMClient, fake_llm: FakeLLM, tmp_path: Path
) -> None:
    """So the next diagnosis can see the key the model used, without storing any text."""
    nameless = ok(json.dumps({"topics": [{"caption": "Passwords", "pages": [1]}]}))
    fake_llm.reply(LITE, nameless, nameless)
    job_id = await queue_for(session, module.slides)

    await run_jobs(session, tmp_path)

    detail = await session.scalar(
        select(AIUsage.detail).where(AIUsage.job_id == job_id, AIUsage.outcome == "invalid_json")
    )
    assert detail is not None
    assert detail.startswith("an object had keys ['caption', 'pages'] but no 'name'")
    assert "Passwords" not in detail
