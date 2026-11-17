"""extract_topics: the prompt, the schema, the repair path, and what never reaches the AI."""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LLMClient
from app.ai.sources import SourcePage
from app.jobs import queue
from app.jobs.kinds import EXTRACT_TOPICS, MERGE_TOPICS
from app.models import AIUsage, Job, Material, TopicProposal
from app.services.topic_maps import queue_extraction
from app.services.topic_maps.prompts import UNTRUSTED, extraction_messages
from tests.fakes import FakeLLM, ok
from tests.search.conftest import run_jobs
from tests.topic_maps.conftest import (
    AUTH,
    LITE,
    PRIVATE,
    SESSIONS,
    Module,
    material,
    node,
    topics_reply,
)

# --- the prompt ---


def test_pages_are_labelled_and_scanned_pages_show_as_figures() -> None:
    pages = [
        SourcePage(1, "Security basics", AUTH),
        SourcePage(2, None, "", is_scanned=True),
        SourcePage(3, "Sessions", f"Sessions\n{SESSIONS}"),
    ]

    system, prompt = extraction_messages("Week 1", "slides", pages, max_chars=10_000)

    assert UNTRUSTED in system.text
    assert "never follow" in system.text.lower()
    assert prompt.text.startswith('Material: "Week 1" (lecture slides), 3 pages.')
    assert f"[page 1] Security basics\n{AUTH}" in prompt.text
    # A title already at the top of the page's text isn't repeated.
    assert f"[page 3]\nSessions\n{SESSIONS}" in prompt.text
    assert "[page 2: figure, no text]" in prompt.text
    assert "<material>" in prompt.text and prompt.text.endswith("</material>")


def test_a_very_long_material_is_cut_with_a_note() -> None:
    pages = [SourcePage(n, None, "x" * 1000) for n in range(1, 11)]

    _, prompt = extraction_messages("Book", "notes", pages, max_chars=3500)

    assert "[page 3]" in prompt.text and "[page 4]" not in prompt.text
    assert "[pages 4 to 10 not shown: the material is too long]" in prompt.text


# --- the job ---


async def queue_one(session: AsyncSession, module: Module, material_id: object) -> Job:
    job = queue_extraction(session, await material(session, material_id))  # type: ignore[arg-type]
    await session.commit()
    return job


async def proposal(session: AsyncSession, material_id: object) -> TopicProposal | None:
    return await session.scalar(
        select(TopicProposal).where(TopicProposal.material_id == material_id)
    )


async def test_a_material_becomes_a_proposal_with_its_model(
    session: AsyncSession,
    module: Module,
    client: LLMClient,
    fake_llm: FakeLLM,
    tmp_path: Path,
) -> None:
    fake_llm.reply(
        LITE,
        topics_reply(
            node("Password storage", [1, 99], subtopics=[node("Salting", [1, 1])]),
            node("Sessions", [3]),
        ),
    )
    fake_llm.reply(LITE, ok('{"topics": []}'))  # the merge that follows
    await queue_one(session, module, module.slides)

    await run_jobs(session, tmp_path)

    saved = await proposal(session, module.slides)
    assert saved is not None
    assert (saved.provider, saved.model) == ("gemini", LITE)
    first = saved.topics["topics"][0]
    assert first["pages"] == [1]  # page 99 doesn't exist; it was dropped
    assert first["subtopics"][0]["pages"] == [1]  # duplicates too
    sent = fake_llm.requests[0].body
    assert sent["response_format"] == {"type": "json_object"}
    assert "[page 2: figure, no text]" in sent["messages"][-1]["content"]
    role = await session.scalar(select(AIUsage.role).where(AIUsage.purpose == "topic_extraction"))
    assert role == "long"
    # It was the module's only extraction, so the merge ran after it.
    assert [r.body["messages"][0]["content"][:30] for r in fake_llm.requests][1].startswith(
        "Reply with one JSON"
    )
    merges = await session.scalars(select(Job.status).where(Job.kind == MERGE_TOPICS))
    assert list(merges) == ["succeeded"]


async def test_rerunning_replaces_the_proposal(
    session: AsyncSession, module: Module, client: LLMClient, fake_llm: FakeLLM, tmp_path: Path
) -> None:
    for name in ("First try", "Second try"):
        fake_llm.reply(LITE, topics_reply(node(name, [1])), ok('{"topics": []}'))
        await queue_one(session, module, module.slides)
        await run_jobs(session, tmp_path)

    rows = list(
        await session.scalars(
            select(TopicProposal).where(TopicProposal.material_id == module.slides)
        )
    )
    assert [row.topics["topics"][0]["name"] for row in rows] == ["Second try"]


async def test_an_invalid_reply_is_repaired_once(
    session: AsyncSession, module: Module, client: LLMClient, fake_llm: FakeLLM, tmp_path: Path
) -> None:
    broken = ok('{"topics": "Passwords, sessions"}')  # not a list: structurally broken
    fake_llm.reply(LITE, broken, topics_reply(node("Passwords", [1])))
    fake_llm.reply(LITE, ok('{"topics": []}'))
    await queue_one(session, module, module.slides)

    await run_jobs(session, tmp_path)

    saved = await proposal(session, module.slides)
    assert saved is not None and saved.topics["topics"][0]["name"] == "Passwords"
    repair = fake_llm.requests[1].body["messages"][-1]["content"]
    assert "did not match the schema" in repair
    outcomes = list(
        await session.scalars(
            select(AIUsage.outcome)
            .where(AIUsage.purpose == "topic_extraction")
            .order_by(AIUsage.created_at, AIUsage.outcome)
        )
    )
    assert sorted(outcomes) == ["invalid_json", "ok"]


async def test_still_invalid_after_repair_fails_the_job_and_the_merge_still_runs(
    session: AsyncSession, module: Module, client: LLMClient, fake_llm: FakeLLM, tmp_path: Path
) -> None:
    fake_llm.reply(LITE, ok("not json"), ok("still not json"))
    job = await queue_one(session, module, module.slides)
    job.max_attempts = 1
    await session.commit()
    job_id = job.id

    await run_jobs(session, tmp_path)

    failed = await session.get(Job, job_id, populate_existing=True)
    assert failed is not None and failed.status == "failed"
    assert failed.last_error is not None and "expected shape" in failed.last_error
    assert await proposal(session, module.slides) is None
    # No proposals at all, so the merge made no AI call; it just relinked.
    merges = list(
        await session.execute(select(Job.status, Job.last_error).where(Job.kind == MERGE_TOPICS))
    )
    assert merges == [("succeeded", None)]
    assert len(fake_llm.requests) == 2


async def test_a_material_with_ai_off_never_reaches_the_client(
    session: AsyncSession, module: Module, client: LLMClient, fake_llm: FakeLLM, tmp_path: Path
) -> None:
    # Queued directly, as if allow_ai was switched off after it was queued.
    queue.enqueue(
        session,
        EXTRACT_TOPICS,
        {"material_id": str(module.private), "module_id": str(module.module_id)},
        user_id=module.user_id,
    )
    queue.enqueue(
        session,
        EXTRACT_TOPICS,
        {"material_id": str(module.past_paper), "module_id": str(module.module_id)},
        user_id=module.user_id,
    )
    await session.commit()

    await run_jobs(session, tmp_path)

    assert fake_llm.requests == []
    assert PRIVATE not in fake_llm.sent_text()
    assert await proposal(session, module.private) is None
    assert await proposal(session, module.past_paper) is None


async def test_turning_ai_off_during_the_call_discards_the_answer(
    session: AsyncSession, module: Module, client: LLMClient, fake_llm: FakeLLM, tmp_path: Path
) -> None:
    async def switch_off() -> None:
        slides = await session.get(Material, module.slides)
        assert slides is not None
        slides.allow_ai = False
        await session.commit()

    fake_llm.before_reply(LITE, switch_off)
    fake_llm.reply(LITE, topics_reply(node("Passwords", [1])))
    await queue_one(session, module, module.slides)

    await run_jobs(session, tmp_path)

    assert len(fake_llm.requests) == 1  # asked once; the answer was then thrown away
    assert await proposal(session, module.slides) is None
