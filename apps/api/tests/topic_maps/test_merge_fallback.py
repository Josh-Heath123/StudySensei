"""The merge's fallback (decision 0009): a compact input that fits Groq's tokens-a-minute
limit, and a "request too large" that moves on without using the call cap."""

import logging
import uuid
from collections.abc import Iterator, Sequence
from pathlib import Path

import httpx
import pytest
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import CallBudget, LLMClient, json_instruction
from app.ai.messages import Message, user
from app.ai.usage import count_requests
from app.core.config import get_settings
from app.models import AIUsage, Topic, User
from app.schemas.topic_maps import MaterialTopics, ModuleTopicMap
from app.services.topic_maps.prompts import (
    MERGE_CHARS_PER_TOKEN,
    ExistingTopic,
    MaterialForPrompt,
    estimate_merge_tokens,
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


def request_chars(messages: Sequence[Message]) -> int:
    """What the client sends: the JSON instruction, the system prompt and the prompt."""
    return len(OVERHEAD) + sum(len(m.text) for m in messages)


def request_tokens(messages: Sequence[Message]) -> int:
    return estimate_merge_tokens("".join(m.text for m in messages) + OVERHEAD)


def test_the_compact_merge_input_fits_under_the_token_limit() -> None:
    materials = a_big_module(materials=10)
    existing = [ExistingTopic(uuid.uuid4(), None, f"Ch{n} Overview") for n in range(1, 6)]

    full, _ = merge_messages("COS330", existing, materials)
    compact, refs = merge_messages(
        "COS330", existing, materials, max_tokens=7000, overhead=OVERHEAD
    )

    assert request_tokens(full) > 7000  # with every description it wouldn't fit
    assert request_tokens(compact) <= 7000
    prompt = compact[-1].text
    # Every proposal is still there, by id, name and page count.
    assert len(refs.proposals) == 10 * 5 * 6
    assert "M10.5.5 Subtopic 10.5.5 (1 p)" in prompt
    assert "M1.1 Topic 1.1 name (2 p)" in prompt
    assert "E5 Ch5 Overview" in prompt
    # Descriptions only while they fit: top-level topics first.
    described = prompt.count(DESCRIPTION.strip())
    assert 0 < described < len(refs.proposals)
    assert f"M1.1 Topic 1.1 name (2 p): {DESCRIPTION.strip()}" in prompt
    assert f"M10.5.5 Subtopic 10.5.5 (1 p): {DESCRIPTION.strip()}" not in prompt


# COS330 after PR #22: 21 materials, 460 proposals whose names average 29 characters, and
# 56 existing topics. Its request was 27,216 characters with no descriptions, and Groq
# counted 9,080-9,103 tokens (limit 8,000).
COS330_NAME_CHARS = 29


def _name(label: str, chars: int) -> str:
    return (label + " " + "access control and policy models" * 2)[:chars]


def a_module_like_cos330(name_chars: int) -> tuple[list[ExistingTopic], list[MaterialForPrompt]]:
    """21 materials with 4 topics of 4 subtopics each (420 proposals), and 56 existing topics
    (8 chapters with 6 subtopics each). Proposal names are ``name_chars`` long."""
    roots = [ExistingTopic(uuid.uuid4(), None, f"Ch{n} {_name('Overview', 20)}") for n in range(8)]
    existing = roots + [
        ExistingTopic(uuid.uuid4(), root.id, _name(f"Existing {r}.{c}", name_chars))
        for r, root in enumerate(roots)
        for c in range(6)
    ]
    materials = [
        MaterialForPrompt(
            uuid.uuid4(),
            f"COS330 Chapter {m} Study Notes",
            "notes",
            MaterialTopics.model_validate(
                {
                    "topics": [
                        {
                            "name": _name(f"Topic {m}.{t}", name_chars),
                            "description": DESCRIPTION,
                            "pages": [t, t + 1, t + 2],
                            "subtopics": [
                                {
                                    "name": _name(f"Sub {m}.{t}.{s}", name_chars),
                                    "description": DESCRIPTION,
                                    "pages": [t],
                                }
                                for s in range(1, 5)
                            ],
                        }
                        for t in range(1, 5)
                    ]
                }
            ),
        )
        for m in range(1, 22)
    ]
    return existing, materials


@pytest.mark.xfail(
    strict=True,
    reason=(
        "COS330's 460 proposal names alone (13,336 characters) plus the fixed parts (6,803) "
        "exceed 7,000 tokens x 2.5 characters; topics are never dropped, so Groq refuses the "
        "merge and Gemini takes it. Remove this mark when the input fits."
    ),
)
def test_a_cos330_sized_merge_fits_its_budget() -> None:
    existing, materials = a_module_like_cos330(COS330_NAME_CHARS)
    max_tokens = get_settings().topic_merge_max_tokens

    messages, refs = merge_messages(
        "COS330 Cyber Security", existing, materials, max_tokens=max_tokens, overhead=OVERHEAD
    )

    assert len(existing) == 56 and len(refs.proposals) == 21 * 4 * 5
    assert request_chars(messages) <= max_tokens * MERGE_CHARS_PER_TOKEN


@pytest.fixture
def warnings_logged(caplog: pytest.LogCaptureFixture) -> Iterator[pytest.LogCaptureFixture]:
    """The topic-map logger's warnings, however logging was configured by earlier tests."""
    logger = logging.getLogger("studysensei.topic_maps")
    # Alembic's fileConfig (the migration tests) disables loggers that already exist.
    was_disabled, logger.disabled = logger.disabled, False
    logger.addHandler(caplog.handler)
    caplog.handler.setLevel(logging.WARNING)
    yield caplog
    logger.removeHandler(caplog.handler)
    logger.disabled = was_disabled


def test_an_input_over_budget_with_no_descriptions_is_reported_not_cut(
    warnings_logged: pytest.LogCaptureFixture,
) -> None:
    existing, materials = a_module_like_cos330(COS330_NAME_CHARS)

    messages, refs = merge_messages(
        "COS330", existing, materials, max_tokens=7000, overhead=OVERHEAD
    )

    prompt = messages[-1].text
    assert DESCRIPTION.strip() not in prompt
    # Every proposal is still there.
    assert all(f"{ref} " in prompt for ref in refs.proposals)
    # (Seen once by our handler and once through propagation, when that's on.)
    [message] = {record.getMessage() for record in warnings_logged.records}
    assert "over its budget of 17500" in message
    assert "420 proposals" in message


def test_a_module_that_fits_logs_nothing(warnings_logged: pytest.LogCaptureFixture) -> None:
    merge_messages("COS330", [], a_big_module(materials=2), max_tokens=7000, overhead=OVERHEAD)

    assert warnings_logged.records == []


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
