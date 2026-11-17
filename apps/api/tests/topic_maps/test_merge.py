"""merge_topics: anchoring on existing topics, re-runs adding only new ones, cited pages."""

import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LLMClient
from app.jobs import queue
from app.jobs.kinds import MERGE_TOPICS
from app.models import Topic, TopicPage, TopicProposal
from app.schemas.topic_maps import MaterialTopics
from app.services.topic_maps.prompts import (
    UNTRUSTED,
    ExistingTopic,
    MaterialForPrompt,
    merge_messages,
)
from tests.fakes import FakeLLM, ok
from tests.search.conftest import run_jobs
from tests.topic_maps.conftest import LITE, PRIVATE, Module, node


def merged(name: str, sources: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    return {
        "name": name,
        "description": f"About {name.lower()}.",
        "sources": sources or [],
        **extra,
    }


def tree_reply(*topics: dict[str, Any]) -> Any:
    return ok(json.dumps({"topics": list(topics)}))


async def propose(
    session: AsyncSession, module: Module, material_id: uuid.UUID, *topics: dict[str, Any]
) -> None:
    session.add(
        TopicProposal(
            user_id=module.user_id,
            module_id=module.module_id,
            material_id=material_id,
            provider="gemini",
            model=LITE,
            topics={"topics": list(topics)},
        )
    )
    await session.commit()


async def with_proposals(session: AsyncSession, module: Module) -> None:
    """M1 = the notes ("Databases": M1.1 Normal forms p1), M2 = the slides ("Week 1
    Security": M2.1 Password storage p1 with M2.1.1 Salting, M2.2 Sessions p3)."""
    await propose(
        session,
        module,
        module.slides,
        node("Password storage", [1], subtopics=[node("Salting", [1])]),
        node("Sessions", [3]),
    )
    await propose(session, module, module.notes, node("Normal forms", [1]))


async def merge(session: AsyncSession, module: Module, tmp_path: Path) -> None:
    queue.enqueue(
        session, MERGE_TOPICS, {"module_id": str(module.module_id)}, user_id=module.user_id
    )
    await session.commit()
    await run_jobs(session, tmp_path)


async def topics(session: AsyncSession, module: Module) -> dict[str, Topic]:
    rows = await session.scalars(
        select(Topic)
        .where(Topic.module_id == module.module_id)
        .execution_options(populate_existing=True)
    )
    return {topic.name: topic for topic in rows}


async def test_the_prompt_lists_anchors_and_proposals_but_no_private_material(
    session: AsyncSession, module: Module, client: LLMClient, fake_llm: FakeLLM, tmp_path: Path
) -> None:
    await with_proposals(session, module)
    # A proposal left over from before the student turned AI off for their own answer.
    await propose(session, module, module.private, node(PRIVATE[:60], [1]))
    fake_llm.reply(LITE, tree_reply())

    await merge(session, module, tmp_path)

    prompt = fake_llm.requests[0].body["messages"][-1]["content"]
    system = fake_llm.requests[0].body["messages"][1]["content"]
    assert UNTRUSTED in system
    assert "Module: COS330 Software Architecture" in prompt
    assert "E1 Microservices" in prompt
    assert 'Material M2: "Week 1 Security" (lecture slides)' in prompt
    assert 'Material M1: "Databases" (notes)' in prompt
    assert "M2.1 Password storage: About password storage." in prompt
    assert "  M2.1.1 Salting" in prompt
    assert "M1.1 Normal forms" in prompt
    assert PRIVATE[:30] not in fake_llm.sent_text()
    assert "u00000000" not in fake_llm.sent_text()


async def test_existing_topics_are_never_renamed_moved_or_deleted(
    session: AsyncSession, module: Module, client: LLMClient, fake_llm: FakeLLM, tmp_path: Path
) -> None:
    await with_proposals(session, module)
    before = (await topics(session, module))["Microservices"]
    snapshot = (before.id, before.name, before.description, before.parent_id, before.position)
    fake_llm.reply(
        LITE,
        tree_reply(
            merged(
                "Security",
                subtopics=[
                    merged("Password storage", ["M2.1", "M2.1.1"]),
                    merged("Sessions", ["M2.2"]),
                    # The AI tries to move and rename the student's topic.
                    merged("Micro-service architecture", existing="E1"),
                ],
            ),
            merged(
                "Renamed microservices",
                existing="E1",
                subtopics=[merged("Service discovery")],
            ),
        ),
    )

    await merge(session, module, tmp_path)

    found = await topics(session, module)
    kept = found["Microservices"]
    assert (kept.id, kept.name, kept.description, kept.parent_id, kept.position) == snapshot
    assert kept.source == "user"
    assert "Renamed microservices" not in found and "Micro-service architecture" not in found
    security = found["Security"]
    assert (security.source, security.parent_id, security.position) == ("ai", None, 1)
    assert found["Password storage"].parent_id == security.id
    assert [found["Password storage"].position, found["Sessions"].position] == [0, 1]
    # New subtopics may go under an existing topic.
    assert found["Service discovery"].parent_id == kept.id
    assert all(found[n].source == "ai" for n in ("Security", "Sessions", "Service discovery"))


async def test_cited_pages_are_kept_per_topic(
    session: AsyncSession, module: Module, client: LLMClient, fake_llm: FakeLLM, tmp_path: Path
) -> None:
    await with_proposals(session, module)
    fake_llm.reply(
        LITE,
        tree_reply(
            merged(
                "Security",
                ["M2.1", "M2.2"],
                subtopics=[merged("Password storage", ["M2.1.1", "M9.9"])],
            ),
            merged("Databases", ["M1.1"]),
        ),
    )

    await merge(session, module, tmp_path)

    found = await topics(session, module)
    rows = await session.execute(
        select(TopicPage.topic_id, TopicPage.material_id, TopicPage.page_number)
    )
    pages = {(topic_id, material_id, page) for topic_id, material_id, page in rows}
    assert pages == {
        (found["Security"].id, module.slides, 1),
        (found["Security"].id, module.slides, 3),
        (found["Password storage"].id, module.slides, 1),  # an unknown id ("M9.9") is ignored
        (found["Databases"].id, module.notes, 1),
    }


async def test_rerunning_adds_only_topics_that_arent_there_yet(
    session: AsyncSession, module: Module, client: LLMClient, fake_llm: FakeLLM, tmp_path: Path
) -> None:
    await with_proposals(session, module)
    first = tree_reply(merged("Security", subtopics=[merged("Password storage", ["M2.1"])]))
    fake_llm.reply(LITE, first)
    await merge(session, module, tmp_path)
    names_after_first = set(await topics(session, module))

    fake_llm.reply(
        LITE,
        tree_reply(
            # The same topics again (one in different case), and one new one.
            merged("security", subtopics=[merged("Password Storage"), merged("Sessions")]),
        ),
    )
    await merge(session, module, tmp_path)

    found = await topics(session, module)
    assert set(found) == names_after_first | {"Sessions"}
    assert found["Sessions"].parent_id == found["Security"].id


async def test_a_topic_the_student_edited_is_left_alone_by_a_rerun(
    session: AsyncSession, module: Module, client: LLMClient, fake_llm: FakeLLM, tmp_path: Path
) -> None:
    await with_proposals(session, module)
    fake_llm.reply(LITE, tree_reply(merged("Security", ["M2.1"])))
    await merge(session, module, tmp_path)
    security = (await topics(session, module))["Security"]
    security.name, security.source = "Keeping systems safe", "user"
    await session.commit()

    # The AI suggests a different name for it by its id.
    fake_llm.reply(LITE, tree_reply(merged("Security and privacy", existing="E2")))
    await merge(session, module, tmp_path)

    found = await topics(session, module)
    assert "Security and privacy" not in found
    assert found["Keeping systems safe"].source == "user"


async def test_no_proposals_means_no_ai_call(
    session: AsyncSession, module: Module, client: LLMClient, fake_llm: FakeLLM, tmp_path: Path
) -> None:
    await merge(session, module, tmp_path)

    assert fake_llm.requests == []
    assert set(await topics(session, module)) == {"Microservices"}


def test_the_merge_prompt_asks_for_the_modules_naming_style_and_whole_chapters() -> None:
    existing = [
        ExistingTopic(uuid.uuid4(), None, "Ch1 Overview"),
        ExistingTopic(uuid.uuid4(), None, "Ch2 Cryptography"),
    ]
    existing.append(ExistingTopic(uuid.uuid4(), existing[0].id, "Security goals"))
    materials = [
        MaterialForPrompt(uuid.uuid4(), "CH09", "slides", MaterialTopics(topics=[])),
    ]

    (system, prompt), _ = merge_messages("COS330 Computer Security", existing, materials)

    assert 'Name new top-level topics in the style of: "Ch1 Overview"; "Ch2 Cryptography"' in (
        prompt.text
    )
    assert "Security goals" not in prompt.text.split("style of:")[1].split("\n")[0]
    assert '"Ch4 Access Control"' in system.text
    assert "keeps\n  its own top-level topic" in system.text
    assert "Don't fold one chapter into another" in system.text


def test_without_top_level_topics_there_is_no_style_line() -> None:
    (_, prompt), _ = merge_messages("COS330", [], [])

    assert "style of" not in prompt.text
