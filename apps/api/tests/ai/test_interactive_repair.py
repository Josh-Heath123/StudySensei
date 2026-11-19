"""Interactive JSON (ADR 0014, amending 0013): a repair turned away moves on, afresh.

The repair goes to the model that wrote the reply. If that model turns it away (429, 503,
413), the next model gets the original prompt, never the first model's reply to fix.
Background calls keep their behaviour (a short wait, then the repair goes on).
"""

import json

import httpx
import pytest
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.errors import AIInvalidOutput, AIUnavailable
from app.models import User
from tests.ai.conftest import MakeClient, Sleeps
from tests.ai.test_client import MESSAGES, outcomes
from tests.fakes import FakeLLM, ok, overloaded, rate_limited, server_error


class Names(BaseModel):
    names: list[str]


GOOD = ok(json.dumps({"names": ["a"]}))


def bad() -> httpx.Response:
    return ok('{"title": "not names"}')


def too_large() -> httpx.Response:
    return httpx.Response(413, json={"error": {"message": "Request too large"}})


def roles_sent(fake_llm: FakeLLM, model: str) -> list[list[str]]:
    return [[m["role"] for m in r.body["messages"]] for r in fake_llm.requests if r.model == model]


@pytest.mark.parametrize("turned_away", [rate_limited, overloaded, too_large])
async def test_a_repair_turned_away_moves_to_the_next_model_afresh(
    make_client: MakeClient,
    fake_llm: FakeLLM,
    sleeps: Sleeps,
    session: AsyncSession,
    user_a: User,
    turned_away: object,
) -> None:
    fake_llm.reply("flash", bad(), turned_away())  # type: ignore[operator]
    fake_llm.reply("oss-120b", GOOD)

    result = await make_client().complete_json_result(
        "smart", MESSAGES, Names, purpose="tutor_quiz", user_id=user_a.id, interactive=True
    )

    assert (result.value.names, result.route.key) == (["a"], "groq/oss-120b")
    assert sleeps.seconds == []  # nobody waits
    # Flash got the prompt, then its own reply back to repair; Groq only the original prompt.
    assert roles_sent(fake_llm, "flash") == [
        ["system", "system", "user"],
        ["system", "system", "user", "assistant", "user"],
    ]
    assert roles_sent(fake_llm, "oss-120b") == [["system", "system", "user"]]
    groq_text = json.dumps(fake_llm.requests[-1].body)
    assert "not names" not in groq_text and "did not match the schema" not in groq_text


async def test_the_repair_goes_to_the_same_model(
    make_client: MakeClient, fake_llm: FakeLLM, session: AsyncSession, user_a: User
) -> None:
    fake_llm.reply("flash", bad(), GOOD)

    result = await make_client().complete_json_result(
        "smart", MESSAGES, Names, purpose="tutor_quiz", user_id=user_a.id, interactive=True
    )

    assert result.route.key == "gemini/flash"
    assert [r.model for r in fake_llm.requests] == ["flash", "flash"]
    assert await outcomes(session, user_a.id) == [
        ("gemini/flash", "invalid_json"),
        ("gemini/flash", "ok"),
    ]


async def test_the_fresh_call_gets_its_own_repair(
    make_client: MakeClient, fake_llm: FakeLLM, user_a: User
) -> None:
    fake_llm.reply("flash", bad(), overloaded())
    fake_llm.reply("oss-120b", bad(), GOOD)

    result = await make_client().complete_json_result(
        "smart", MESSAGES, Names, purpose="tutor_quiz", user_id=user_a.id, interactive=True
    )

    assert result.route.key == "groq/oss-120b"
    assert [r.model for r in fake_llm.requests] == ["flash", "flash", "oss-120b", "oss-120b"]


async def test_still_invalid_after_the_repair_is_invalid_output(
    make_client: MakeClient, fake_llm: FakeLLM, user_a: User
) -> None:
    fake_llm.reply("flash", bad(), bad())

    with pytest.raises(AIInvalidOutput, match="after a repair attempt"):
        await make_client().complete_json_result(
            "smart", MESSAGES, Names, purpose="tutor_quiz", user_id=user_a.id, interactive=True
        )
    assert [r.model for r in fake_llm.requests] == ["flash", "flash"]


async def test_a_server_error_on_the_repair_fails_at_once(
    make_client: MakeClient, fake_llm: FakeLLM, sleeps: Sleeps, user_a: User
) -> None:
    fake_llm.reply("flash", bad(), server_error())

    with pytest.raises(AIUnavailable) as unavailable:
        await make_client().complete_json_result(
            "smart", MESSAGES, Names, purpose="tutor_quiz", user_id=user_a.id, interactive=True
        )
    assert not unavailable.value.exhausted
    assert [r.model for r in fake_llm.requests] == ["flash", "flash"]
    assert sleeps.seconds == []


async def test_when_every_model_turns_it_away_it_says_when_to_retry(
    make_client: MakeClient, fake_llm: FakeLLM, user_a: User
) -> None:
    fake_llm.reply("flash", bad(), rate_limited(retry_after=30))
    fake_llm.reply("oss-120b", overloaded())

    with pytest.raises(AIUnavailable) as unavailable:
        await make_client().complete_json_result(
            "smart", MESSAGES, Names, purpose="tutor_quiz", user_id=user_a.id, interactive=True
        )
    assert unavailable.value.exhausted
    assert unavailable.value.retry_at is not None


async def test_background_calls_keep_waiting_then_repairing(
    make_client: MakeClient, fake_llm: FakeLLM, sleeps: Sleeps, user_a: User
) -> None:
    """Unchanged for jobs: a short wait on the busy model, then the repair continues."""
    fake_llm.reply("flash", bad(), rate_limited(), GOOD)

    result = await make_client().complete_json_result(
        "smart", MESSAGES, Names, purpose="topic_extraction", user_id=user_a.id
    )

    assert result.route.key == "gemini/flash"
    assert sleeps.seconds == [2.0]
    assert roles_sent(fake_llm, "flash")[-1] == ["system", "system", "user", "assistant", "user"]
