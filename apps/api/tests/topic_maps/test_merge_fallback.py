"""The merge's fallback (decision 0009): a compact input that fits Groq's tokens-a-minute
limit, and a "request too large" that moves on without using the call cap."""

import uuid
from collections.abc import Sequence
from pathlib import Path

import httpx
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import CallBudget, LLMClient, json_instruction
from app.ai.messages import Message, user
from app.ai.usage import count_requests
from app.models import AIUsage, Topic, User
from app.schemas.topic_maps import MaterialTopics, ModuleTopicMap
from app.services.topic_maps.prompts import (
    ExistingTopic,
    MaterialForPrompt,
    estimate_tokens,
    merge_messages,
)
from tests.ai.conftest import NOW, MakeClient, routes
from tests.fakes import FakeLLM, ok, overloaded
from tests.topic_maps.conftest import LITE, Module
from tests.topic_maps.test_merge import merge, merged, tree_reply, with_proposals

OVERHEAD = json_instruction(ModuleTopicMap)
DESCRIPTION = "A sentence about what this part of the course covers, as the AI wrote it. " * 2


def a_big_module(
    materials: int = 16, topics: int = 5, subtopics: int = 5
) -> list[MaterialForPrompt]:
    """Synthetic proposals the size of a real module (COS330 had 460), long descriptions."""
    return [
        MaterialForPrompt(
            uuid.uuid4(),
            f"Chapter {m} notes",
            "notes",
            MaterialTopics.model_validate(
                {
                    "topics": [
                        {
                            "name": f"Topic {m}.{t} name",
                            "description": DESCRIPTION,
                            "pages": [t, t + 1],
                            "subtopics": [
                                {
                                    "name": f"Subtopic {m}.{t}.{s}",
                                    "description": DESCRIPTION,
                                    "pages": [t],
                                }
                                for s in range(1, subtopics + 1)
                            ],
                        }
                        for t in range(1, topics + 1)
                    ]
                }
            ),
        )
        for m in range(1, materials + 1)
    ]


def request_tokens(messages: Sequence[Message]) -> int:
    return estimate_tokens("".join(m.text for m in messages) + OVERHEAD)


def test_the_compact_merge_input_fits_under_the_token_limit() -> None:
    materials = a_big_module()
    existing = [ExistingTopic(uuid.uuid4(), None, f"Ch{n} Overview") for n in range(1, 6)]

    full, _ = merge_messages("COS330", existing, materials)
    compact, refs = merge_messages(
        "COS330", existing, materials, max_tokens=7000, overhead=OVERHEAD
    )

    assert request_tokens(full) > 7000  # with every description it wouldn't fit
    assert request_tokens(compact) <= 7000
    prompt = compact[-1].text
    # Every proposal is still there, by id, name and page count.
    assert len(refs.proposals) == 16 * 5 * 6
    assert "M16.5.5 Subtopic 16.5.5 (1 p)" in prompt
    assert "M1.1 Topic 1.1 name (2 p)" in prompt
    assert "E5 Ch5 Overview" in prompt
    # Descriptions only while they fit: top-level topics first.
    described = prompt.count(DESCRIPTION.strip())
    assert 0 < described < len(refs.proposals)
    assert f"M1.1 Topic 1.1 name (2 p): {DESCRIPTION.strip()}" in prompt
    assert f"M16.5.5 Subtopic 16.5.5 (1 p): {DESCRIPTION.strip()}" not in prompt


def test_a_small_module_keeps_every_description() -> None:
    materials = a_big_module(materials=2, topics=2, subtopics=1)

    messages, refs = merge_messages("COS330", [], materials, max_tokens=7000, overhead=OVERHEAD)

    assert messages[-1].text.count(DESCRIPTION.strip()) == len(refs.proposals) == 8


async def test_groq_takes_the_merge_when_gemini_is_busy(
    session: AsyncSession, module: Module, client: LLMClient, fake_llm: FakeLLM, tmp_path: Path
) -> None:
    await with_proposals(session, module)
    fake_llm.reply(LITE, overloaded(), overloaded())
    fake_llm.reply("oss-120b", tree_reply(merged("Security", ["M2.1"])))

    await merge(session, module, tmp_path)

    groq = [r for r in fake_llm.requests if r.model == "oss-120b"]
    assert len(groq) == 1
    names = set(
        await session.scalars(select(Topic.name).where(Topic.module_id == module.module_id))
    )
    assert "Security" in names


# --- 413: too large for one model ---


class Names(BaseModel):
    names: list[str]


async def test_a_request_too_large_moves_on_without_using_the_cap(
    make_client: MakeClient, fake_llm: FakeLLM, session: AsyncSession, user_a: User
) -> None:
    # Groq first, so its 413 comes before Gemini answers.
    client = make_client(ai_smart=routes("groq/oss-120b", "gemini/flash"))
    too_large = httpx.Response(
        413, json={"error": {"message": "Request too large for model on tokens per minute"}}
    )
    fake_llm.reply("oss-120b", too_large)
    fake_llm.reply("flash", ok('{"names": ["Big one"]}'))
    budget = CallBudget(limit=1, turned_away_limit=5)

    result = await client.complete_json(
        "smart", [user("Topics?")], Names, purpose="t", user_id=user_a.id, budget=budget
    )

    assert result.names == ["Big one"]
    assert (budget.used, budget.turned_away) == (1, 1)
    outcome, detail = (
        await session.execute(
            select(AIUsage.outcome, AIUsage.detail).where(AIUsage.model == "oss-120b")
        )
    ).one()
    assert outcome == "too_large" and "HTTP 413" in (detail or "")
    # Not counted toward Groq's daily budget, and Groq isn't cooled down: a smaller request
    # goes straight to it.
    since = NOW.replace(year=NOW.year - 1)
    assert (
        await count_requests(
            session, user_id=user_a.id, provider="groq", model="oss-120b", since=since
        )
        == 0
    )
    fake_llm.reply("oss-120b", ok("Small answer"))
    text = await client.complete_text("smart", [user("Hi")], purpose="t", user_id=user_a.id)
    assert text == "Small answer"
