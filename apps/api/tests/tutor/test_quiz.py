"""'Quiz me': the schema and repair, grounding, fewer than 3, grading, and saved answers."""

import json
from typing import Any

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AIUsage, Message, User
from app.schemas.tutor import Quiz
from app.services.tutor.quiz import grade, keep_grounded
from tests.api.conftest import ClientFactory
from tests.fakes import FakeEmbedder, FakeLLM, ok, overloaded, rate_limited, streamed
from tests.tutor.conftest import FIREWALL, Module, sse_events


def question(n: int, sources: list[str] | None = None, correct: int = 1) -> dict[str, Any]:
    return {
        "prompt": f"Question {n}: what does a stateful firewall track?",
        "options": ["Nothing", "Each connection", "Only ports", "Only addresses"],
        "correct": correct,
        "explanation": "It keeps a state table of connections [S1].",
        "sources": sources or ["S1"],
    }


def quiz_reply(*questions: dict[str, Any]) -> httpx.Response:
    return ok(json.dumps({"questions": list(questions)}))


async def alice(client_as: ClientFactory, session: AsyncSession, module: Module) -> Any:
    user = await session.get(User, module.user_id)
    assert user is not None
    return client_as(user)


async def answered(api: httpx.AsyncClient, module: Module, fake_llm: FakeLLM) -> str:
    """A conversation with one answered question; returns its id."""
    fake_llm.reply("flash", streamed("It tracks each connection [S1]."))
    created = await api.post(f"/modules/{module.module_id}/tutor/conversations", json={})
    conversation_id = str(created.json()["id"])
    response = await api.post(
        f"/conversations/{conversation_id}/messages",
        json={"question": "How does a stateful inspection firewall work?"},
    )
    assert sse_events(response.text)[-1][0] == "done"
    return conversation_id


# --- the schema ---


def test_a_well_formed_quiz_validates_and_labels_are_normalised() -> None:
    quiz = Quiz.model_validate(
        {"questions": [question(1, ["[S1]", "【S2】", "s3"]), {**question(2), "extra": "x"}]}
    )

    assert quiz.questions[0].sources == ["S1", "S2", "S3"]
    assert len(quiz.questions) == 2


@pytest.mark.parametrize(
    "broken",
    [
        {"options": ["a", "b", "c"]},
        {"options": ["a", "b", "c", "d", "e"]},
        {"correct": 4},
        {"correct": -1},
        {"sources": []},
        {"prompt": ""},
        {"explanation": " "},
    ],
)
def test_a_malformed_question_is_rejected(broken: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Quiz.model_validate({"questions": [{**question(1), **broken}]})


def test_grading_is_deterministic_code() -> None:
    quiz = Quiz.model_validate(
        {"questions": [question(1, correct=1), question(2, correct=3), question(3, correct=0)]}
    )

    assert grade(quiz, [1, 2, None]) == [True, False, None]
    assert grade(quiz, [1, 3, 0]) == [True, True, True]
    assert grade(quiz, []) == [None, None, None]


def test_questions_not_grounded_in_the_sources_are_dropped() -> None:
    quiz = Quiz.model_validate(
        {
            "questions": [
                question(1, ["S1"]),
                question(2, ["S9"]),
                question(3, ["S1", "S4"]),
                question(4, ["S2"]),
                question(5, ["S2"]),
            ]
        }
    )

    kept, dropped = keep_grounded(quiz, ["S1", "S2", "S3"])

    assert kept is not None
    assert [q.prompt[:10] for q in kept.questions] == ["Question 1", "Question 4", "Question 5"]
    assert dropped == 0  # three were asked for, and three good ones came back
    two, missing = keep_grounded(
        Quiz.model_validate({"questions": [question(1), question(2, ["S7"])]}), ["S1"]
    )
    assert two is not None and len(two.questions) == 1 and missing == 1
    assert keep_grounded(Quiz.model_validate({"questions": [question(1, ["S9"])]}), ["S1"]) == (
        None,
        1,
    )


# --- the endpoint ---


async def test_quiz_me_writes_three_questions_on_the_last_answers_sources(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
    fake_embedder: FakeEmbedder,
) -> None:
    async with await alice(client_as, session, module) as api:
        conversation_id = await answered(api, module, fake_llm)
        fake_embedder.query_calls.clear()
        fake_llm.reply("flash", quiz_reply(question(1), question(2), question(3)))
        response = await api.post(f"/conversations/{conversation_id}/quiz")
        stored = (await api.get(f"/conversations/{conversation_id}")).json()["messages"]

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["role"], body["mode"], body["status"]) == ("assistant", "quiz", "complete")
    assert body["model"] == "gemini/flash"
    assert body["text"] == "Quiz: 3 questions."
    assert len(body["quiz"]["questions"]) == 3
    assert body["quiz_answers"] == [None, None, None]
    assert body["first_token_ms"] is None and body["total_ms"] >= 0
    # The same sources as the answer, and the ones the questions use marked cited.
    assert next((s["label"], s["cited"]) for s in body["sources"]) == ("S1", True)
    assert [s["label"] for s in body["sources"]] == [s["label"] for s in stored[1]["sources"]]
    assert [(m["role"], m["mode"], m["text"]) for m in stored[2:]] == [
        ("user", "quiz", "Quiz me"),
        ("assistant", "quiz", "Quiz: 3 questions."),
    ]
    # No new search: the answer's own passages, sent as JSON-mode chat.
    assert fake_embedder.query_calls == []
    sent = fake_llm.requests[-1].body
    assert sent["response_format"] == {"type": "json_object"}
    assert FIREWALL[:40] in sent["messages"][-1]["content"]
    assert "How does a stateful inspection firewall work?" in sent["messages"][-1]["content"]


async def test_a_malformed_quiz_gets_one_repair(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
) -> None:
    async with await alice(client_as, session, module) as api:
        conversation_id = await answered(api, module, fake_llm)
        three_options = {**question(1), "options": ["a", "b", "c"]}
        fake_llm.reply("flash", quiz_reply(three_options), quiz_reply(question(1), question(2)))
        response = await api.post(f"/conversations/{conversation_id}/quiz")

    assert response.status_code == 201
    assert len(response.json()["quiz"]["questions"]) == 2
    repair = fake_llm.requests[-1].body["messages"][-1]["content"]
    assert "did not match the schema" in repair
    outcomes = [
        row
        for (row,) in await session.execute(
            select(AIUsage.outcome).where(AIUsage.purpose == "tutor_quiz")
        )
    ]
    assert sorted(outcomes) == ["invalid_json", "ok"]


async def test_still_malformed_after_the_repair_is_a_failed_answer_saying_so(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
) -> None:
    async with await alice(client_as, session, module) as api:
        conversation_id = await answered(api, module, fake_llm)
        fake_llm.reply("flash", ok("not json"), ok('{"questions": []}'))
        response = await api.post(f"/conversations/{conversation_id}/quiz")

    body = response.json()
    assert (response.status_code, body["status"], body["quiz"]) == (201, "failed", None)
    assert "didn't come out right" in body["text"]


async def test_ungrounded_questions_are_dropped_and_fewer_than_three_are_kept(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
) -> None:
    async with await alice(client_as, session, module) as api:
        conversation_id = await answered(api, module, fake_llm)
        fake_llm.reply(
            "flash", quiz_reply(question(1), question(2, ["S9"]), question(3, ["S1", "S8"]))
        )
        response = await api.post(f"/conversations/{conversation_id}/quiz")

    body = response.json()
    assert body["status"] == "complete"
    assert [q["prompt"][:10] for q in body["quiz"]["questions"]] == ["Question 1"]
    assert body["text"] == "Quiz: 1 question."
    assert body["quiz_answers"] == [None]


async def test_no_grounded_question_at_all_is_a_failed_answer(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
) -> None:
    async with await alice(client_as, session, module) as api:
        conversation_id = await answered(api, module, fake_llm)
        fake_llm.reply("flash", quiz_reply(question(1, ["S9"])))
        response = await api.post(f"/conversations/{conversation_id}/quiz")

    body = response.json()
    assert (body["status"], body["quiz"]) == ("failed", None)
    assert body["text"] == "None of the questions it wrote were based on your sources."


async def test_a_quiz_needs_an_answer_first(
    client_as: ClientFactory, session: AsyncSession, module: Module, tutor_llm: object
) -> None:
    async with await alice(client_as, session, module) as api:
        created = await api.post(f"/modules/{module.module_id}/tutor/conversations", json={})
        response = await api.post(f"/conversations/{created.json()['id']}/quiz")

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Ask a question first: the quiz is made from the last answer's sources."
    )


async def test_busy_models_are_skipped_without_waiting_then_503_says_when(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
    sleeps: Any,
) -> None:
    async with await alice(client_as, session, module) as api:
        conversation_id = await answered(api, module, fake_llm)
        fake_llm.reply("flash", overloaded())
        fake_llm.reply("oss-120b", rate_limited(retry_after=40))
        response = await api.post(f"/conversations/{conversation_id}/quiz")
        stored = (await api.get(f"/conversations/{conversation_id}")).json()["messages"]

    assert response.status_code == 503
    assert int(response.headers["Retry-After"]) >= 1
    assert sleeps.seconds == []  # interactive: no waiting
    assert (stored[-1]["mode"], stored[-1]["status"]) == ("quiz", "failed")


async def test_a_quiz_isnt_history_for_the_next_question(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
) -> None:
    async with await alice(client_as, session, module) as api:
        conversation_id = await answered(api, module, fake_llm)
        fake_llm.reply("flash", quiz_reply(question(1)))
        await api.post(f"/conversations/{conversation_id}/quiz")
        fake_llm.reply("flash", streamed("Again [S1]."))
        await api.post(
            f"/conversations/{conversation_id}/messages",
            json={"question": "Explain that differently", "mode": "explain_differently"},
        )

    sent = fake_llm.requests[-1].body["messages"]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"]
    assert "Quiz" not in sent[2]["content"]


async def test_quiz_mode_isnt_streamed(
    client_as: ClientFactory, session: AsyncSession, module: Module, tutor_llm: object
) -> None:
    async with await alice(client_as, session, module) as api:
        created = await api.post(f"/modules/{module.module_id}/tutor/conversations", json={})
        response = await api.post(
            f"/conversations/{created.json()['id']}/messages",
            json={"question": "Quiz me", "mode": "quiz"},
        )

    assert response.status_code == 422


# --- the student's answers ---


async def test_answers_are_saved_and_graded_by_code(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
) -> None:
    async with await alice(client_as, session, module) as api:
        conversation_id = await answered(api, module, fake_llm)
        fake_llm.reply(
            "flash",
            quiz_reply(question(1, correct=1), question(2, correct=2), question(3, correct=0)),
        )
        quiz_id = (await api.post(f"/conversations/{conversation_id}/quiz")).json()["id"]
        first = await api.patch(
            f"/messages/{quiz_id}/quiz-answers", json={"answers": [1, None, None]}
        )
        all_three = await api.patch(
            f"/messages/{quiz_id}/quiz-answers", json={"answers": [1, 3, 0]}
        )
        stored = (await api.get(f"/conversations/{conversation_id}")).json()["messages"][-1]

    assert first.status_code == 200
    assert first.json()["quiz_answers"] == [1, None, None]
    assert all_three.json()["quiz_answers"] == [1, 3, 0]
    assert stored["quiz_answers"] == [1, 3, 0]
    message = await session.get(Message, stored["id"])
    assert message is not None and message.quiz is not None
    from app.schemas.tutor import Quiz as QuizSchema

    assert grade(QuizSchema.model_validate(message.quiz), [1, 3, 0]) == [True, False, True]


@pytest.mark.parametrize(
    "answers",
    [[1, None], [1, None, None, None], [4, None, None], [-1, None, None], ["b", None, None]],
)
async def test_answers_that_dont_fit_the_quiz_are_rejected(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
    answers: list[Any],
) -> None:
    async with await alice(client_as, session, module) as api:
        conversation_id = await answered(api, module, fake_llm)
        fake_llm.reply("flash", quiz_reply(question(1), question(2), question(3)))
        quiz_id = (await api.post(f"/conversations/{conversation_id}/quiz")).json()["id"]
        response = await api.patch(f"/messages/{quiz_id}/quiz-answers", json={"answers": answers})

    assert response.status_code == 422


async def test_only_a_quiz_takes_answers(
    client_as: ClientFactory,
    session: AsyncSession,
    module: Module,
    tutor_llm: object,
    fake_llm: FakeLLM,
) -> None:
    async with await alice(client_as, session, module) as api:
        conversation_id = await answered(api, module, fake_llm)
        reply = (await api.get(f"/conversations/{conversation_id}")).json()["messages"][1]
        response = await api.patch(f"/messages/{reply['id']}/quiz-answers", json={"answers": [0]})

    assert (response.status_code, response.json()["detail"]) == (422, "This message isn't a quiz.")
