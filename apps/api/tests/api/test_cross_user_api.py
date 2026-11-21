"""Over HTTP, Bob can't reach Alice's modules, topics, assessments, tasks, sessions, materials,
tutor conversations or planning (availability rules and exceptions, topic workload).

Every request Bob makes with one of Alice's IDs must get exactly the response
a random, non-existent ID gets, so he can't even tell her rows exist. Afterwards
Alice's data must be unchanged.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AIUsage,
    AvailabilityException,
    AvailabilityRule,
    Conversation,
    Material,
    Message,
    PlanBlock,
    PlanVersion,
    TopicReview,
    User,
)
from app.services.push.sender import FakePushSender
from app.storage.local import LocalStorage
from tests.academics.conftest import Rows
from tests.fakes import FakeLLM, ok
from tests.materials import samples

# A start for POST /sessions; it never gets far enough to be stored.
START = {"id": str(uuid.uuid4()), "occurred_at": "2026-11-01T08:00:00Z"}

# (method, path template, body). {module}/{topic}/{assessment}/{task}/{session} are
# filled with Alice's IDs, or with random UUIDs for the baseline. {my_*} are always Bob's.
ATTEMPTS: list[tuple[str, str, dict[str, Any] | None]] = [
    ("GET", "/modules/{module}", None),
    ("PATCH", "/modules/{module}", {"name": "Hacked"}),
    ("DELETE", "/modules/{module}", None),
    ("GET", "/modules/{module}/topics", None),
    ("POST", "/modules/{module}/topics", {"name": "Planted"}),
    ("PATCH", "/topics/{topic}", {"name": "Hacked"}),
    ("POST", "/topics/{topic}/move", {"parent_id": None, "position": 0}),
    ("DELETE", "/topics/{topic}", None),
    # Using her topic as a parent, from Bob's own side.
    ("POST", "/topics/{my_topic}/move", {"parent_id": "{topic}", "position": 0}),
    # Assessments
    ("GET", "/modules/{module}/assessments", None),
    ("GET", "/assessments/{assessment}", None),
    ("PATCH", "/assessments/{assessment}", {"title": "Hacked"}),
    ("DELETE", "/assessments/{assessment}", None),
    ("POST", "/modules/{module}/assessments", {"title": "Planted", "kind": "exam"}),
    # His assessment covering her topic (on create and on update).
    (
        "POST",
        "/modules/{my_module}/assessments",
        {"title": "X", "kind": "exam", "topic_ids": ["{topic}"]},
    ),
    ("PATCH", "/assessments/{my_assessment}", {"topic_ids": ["{topic}"]}),
    # Tasks
    ("GET", "/modules/{module}/tasks", None),
    ("GET", "/tasks/{task}", None),
    ("PATCH", "/tasks/{task}", {"status": "done"}),
    ("DELETE", "/tasks/{task}", None),
    ("POST", "/modules/{module}/tasks", {"title": "Planted"}),
    # His task on her assessment (on create and on update).
    ("POST", "/modules/{my_module}/tasks", {"title": "X", "assessment_id": "{assessment}"}),
    ("PATCH", "/tasks/{my_task}", {"assessment_id": "{assessment}"}),
    # Study sessions
    ("GET", "/sessions/{session}", None),
    (
        "POST",
        "/sessions/{session}/events",
        {
            "events": [
                {"id": str(uuid.uuid4()), "type": "pause", "occurred_at": START["occurred_at"]}
            ]
        },
    ),
    ("PUT", "/sessions/{session}/reflection", {"focus_rating": 1}),
    ("DELETE", "/sessions/{session}", None),
    ("GET", "/modules/{module}/sessions", None),
    ("GET", "/modules/{module}/sessions?limit=5&offset=0", None),
    ("GET", "/modules/{module}/sessions/summary?week_start=2026-11-09T00:00:00Z", None),
    ("POST", "/sessions", {"module_id": "{module}", "start": START}),
    # His session on her topic, and his reflection rating her topic.
    ("POST", "/sessions", {"module_id": "{my_module}", "topic_id": "{topic}", "start": START}),
    (
        "PUT",
        "/sessions/{my_session}/reflection",
        {"focus_rating": 3, "topic_ratings": [{"topic_id": "{topic}", "confidence": 3}]},
    ),
    # Materials (uploads into her module are in test_bob_cannot_upload_into_alices_module)
    ("GET", "/modules/{module}/materials", None),
    ("GET", "/materials/{material}", None),
    ("PATCH", "/materials/{material}", {"title": "Hacked", "allow_ai": True}),
    ("DELETE", "/materials/{material}", None),
    ("POST", "/materials/{material}/retry", None),
    ("GET", "/materials/{material}/pages", None),
    ("GET", "/materials/{material}/pages/1", None),
    # Search
    ("GET", "/modules/{module}/search?q=password", None),
    # Topic maps
    ("GET", "/modules/{module}/topic-map", None),
    ("POST", "/modules/{module}/topic-map/build", None),
    ("GET", "/modules/{module}/topic-map/materials", None),
    ("POST", "/materials/{material}/topics/retry", None),
    ("GET", "/materials/{material}/file", None),
    ("DELETE", "/modules/{module}/ai-topics", None),
    # Topic review (decision 0009)
    ("POST", "/topics/{topic}/keep", None),
    ("POST", "/topics/{topic}/merge-into", {"target_id": "{my_topic}"}),
    # Merging his topic into hers.
    ("POST", "/topics/{my_topic}/merge-into", {"target_id": "{topic}"}),
    ("POST", "/topics/{topic}/dismiss", None),
    ("POST", "/modules/{module}/topics/keep-all", None),
    ("GET", "/modules/{module}/dismissed-topics", None),
    ("POST", "/dismissed-topics/{dismissed}/restore", None),
    ("GET", "/topics/{topic}/pages", None),
    ("DELETE", "/topics/{topic}/pages/{material}/1", None),
    # Unlinking a page of her material from his topic.
    ("DELETE", "/topics/{my_topic}/pages/{material}/1", None),
    # Tutor
    ("POST", "/modules/{module}/tutor/conversations", {}),
    # His conversation on her topic, or for her study session.
    ("POST", "/modules/{my_module}/tutor/conversations", {"topic_id": "{topic}"}),
    ("POST", "/modules/{my_module}/tutor/conversations", {"study_session_id": "{session}"}),
    ("GET", "/conversations/{conversation}", None),
    ("GET", "/modules/{module}/tutor/conversations", None),
    ("GET", "/modules/{module}/tutor/conversations?study_session_id={session}", None),
    ("POST", "/conversations/{conversation}/messages", {"question": "What is a firewall?"}),
    ("POST", "/conversations/{conversation}/quiz", None),
    ("PATCH", "/messages/{message}/quiz-answers", {"answers": [0]}),
    (
        "PATCH",
        "/messages/{message}/voice-timing",
        {
            "voice_latency_ms": 1,
            "transcript_ms": 1,
            "first_token_ms": 1,
            "first_sentence_ms": 1,
        },
    ),
    # Planning
    ("PATCH", "/availability/rules/{rule}", {"start": "06:00"}),
    ("DELETE", "/availability/rules/{rule}", None),
    ("PATCH", "/availability/exceptions/{exception}", {"unavailable": True}),
    ("DELETE", "/availability/exceptions/{exception}", None),
    ("PATCH", "/topics/{topic}/planning", {"confidence": 1, "estimated_minutes": 5}),
    # The stored plan (decision 0021)
    ("POST", "/plan/blocks/{block}/skip", None),
    ("POST", "/plan/blocks/{block}/move", {"start": "2030-01-07T18:00:00Z"}),
    # His session for her planned block.
    (
        "POST",
        "/sessions",
        {
            "module_id": "{my_module}",
            "topic_id": "{my_topic}",
            "plan_block_id": "{block}",
            "start": START,
        },
    ),
]


@pytest.fixture
async def materials(session: AsyncSession, alice: Rows, bob: Rows) -> dict[str, Material]:
    """One failed (so retryable) material each, straight into the database."""
    made = {}
    for name, rows in (("alice", alice), ("bob", bob)):
        material = Material(
            user_id=rows.user.id,
            module_id=rows.module.id,
            kind="slides",
            title="Week 1",
            original_filename="week1.pdf",
            content_type="application/pdf",
            size_bytes=10,
            sha256="b" * 64,
            status="failed",
            error="Couldn't read it.",
            allow_ai=False,
        )
        session.add(material)
        made[name] = material
    await session.commit()
    return made


@pytest.fixture
async def dismissed(session: AsyncSession, alice: Rows, bob: Rows) -> dict[str, TopicReview]:
    """One dismissed AI topic each (so restorable)."""
    made = {}
    for name, rows in (("alice", alice), ("bob", bob)):
        review = TopicReview(
            user_id=rows.user.id,
            module_id=rows.module.id,
            topic_id=uuid.uuid4(),
            name="Dismissed",
            name_key="dismissed",
            outcome="dismissed",
            snapshot={"description": None, "parent_id": None, "pages": []},
        )
        session.add(review)
        made[name] = review
    await session.commit()
    return made


@pytest.fixture
async def conversations(session: AsyncSession, alice: Rows, bob: Rows) -> dict[str, Conversation]:
    """One tutor conversation each, for their own study session, with a quiz in it."""
    made = {}
    for name, rows in (("alice", alice), ("bob", bob)):
        conversation = Conversation(
            user_id=rows.user.id,
            module_id=rows.module.id,
            topic_id=rows.topic.id,
            study_session_id=rows.study_session.id,
        )
        session.add(conversation)
        await session.flush()
        quiz_message = Message(
            user_id=rows.user.id,
            conversation_id=conversation.id,
            position=0,
            role="assistant",
            mode="quiz",
            text="Quiz: 1 question.",
            status="complete",
            quiz={
                "questions": [
                    {
                        "prompt": "Which?",
                        "options": ["a", "b", "c", "d"],
                        "correct": 0,
                        "explanation": "Because [S1].",
                        "sources": ["S1"],
                    }
                ]
            },
            quiz_answers=[None],
        )
        session.add(quiz_message)
        await session.flush()
        _MESSAGES[conversation.id] = quiz_message.id
        made[name] = conversation
    await session.commit()
    return made


_MESSAGES: dict[uuid.UUID, uuid.UUID] = {}


@pytest.fixture
async def availability(
    session: AsyncSession, alice: Rows, bob: Rows
) -> dict[str, tuple[AvailabilityRule, AvailabilityException]]:
    """A Monday 18:00-20:00 rule and an unavailable date each, on the same days (so the
    unique date and the overlap rule are per user too)."""
    made = {}
    for name, rows in (("alice", alice), ("bob", bob)):
        rule = AvailabilityRule(user_id=rows.user.id, weekday=0, start_minute=1080, end_minute=1200)
        exception = AvailabilityException(
            user_id=rows.user.id, date=date(2026, 11, 23), unavailable=True, windows=[]
        )
        session.add_all([rule, exception])
        made[name] = (rule, exception)
    await session.commit()
    return made


@pytest.fixture
async def plan_blocks(session: AsyncSession, alice: Rows, bob: Rows) -> dict[str, PlanBlock]:
    """A current plan version each with one planned block tomorrow, straight into the
    database."""
    made = {}
    now = datetime.now(UTC)
    for name, rows in (("alice", alice), ("bob", bob)):
        version = PlanVersion(
            user_id=rows.user.id,
            number=1,
            trigger="initial",
            summary="Your first plan.",
            generated_at=now,
            checked_at=now,
            days=28,
            report=EMPTY_REPORT,
        )
        session.add(version)
        await session.flush()
        block = PlanBlock(
            user_id=rows.user.id,
            version_id=version.id,
            start_at=now + timedelta(days=1),
            end_at=now + timedelta(days=1, minutes=50),
            module_id=rows.module.id,
            assessment_id=rows.assessment.id,
            topic_id=rows.topic.id,
            kind="study",
            reason="workload",
            method="first_pass",
            reason_text="Why.",
            method_text="How.",
        )
        session.add(block)
        made[name] = block
    await session.commit()
    return made


EMPTY_REPORT: dict[str, Any] = {
    "overall": {
        "required_minutes": 0,
        "planned_minutes": 0,
        "short_minutes": 0,
        "review_minutes": 0,
        "free_minutes": 0,
        "booked_minutes": 0,
        "status": "fits",
        "deadline": None,
        "line": "Nothing is due in the next 28 days.",
    },
    "assessments": [],
    "later": [],
    "levers": [],
    "basis": "",
}


def message_of(conversation: Conversation) -> uuid.UUID:
    """The quiz message the fixture put in the conversation (looked up once, then kept)."""
    return _MESSAGES[conversation.id]


def fill(value: Any, ids: dict[str, str]) -> Any:
    if isinstance(value, str):
        return value.format(**ids)
    if isinstance(value, dict):
        return {k: fill(v, ids) for k, v in value.items()}
    if isinstance(value, list):
        return [fill(v, ids) for v in value]
    return value


def ids_of(
    alice: Rows,
    bob: Rows,
    materials: dict[str, Material],
    dismissed: dict[str, TopicReview],
    conversations: dict[str, Conversation],
    availability: dict[str, tuple[AvailabilityRule, AvailabilityException]],
    plan_blocks: dict[str, PlanBlock],
) -> tuple[dict[str, str], dict[str, str]]:
    """(Alice's real IDs, the same keys with random IDs). Bob's own IDs are in both."""
    mine = {
        "my_module": str(bob.module.id),
        "my_topic": str(bob.topic.id),
        "my_assessment": str(bob.assessment.id),
        "my_task": str(bob.task.id),
        "my_session": str(bob.study_session.id),
        "my_material": str(materials["bob"].id),
        "my_conversation": str(conversations["bob"].id),
        "my_message": str(message_of(conversations["bob"])),
    }
    hers = {
        "module": str(alice.module.id),
        "topic": str(alice.topic.id),
        "assessment": str(alice.assessment.id),
        "task": str(alice.task.id),
        "session": str(alice.study_session.id),
        "material": str(materials["alice"].id),
        "dismissed": str(dismissed["alice"].id),
        "conversation": str(conversations["alice"].id),
        "message": str(message_of(conversations["alice"])),
        "rule": str(availability["alice"][0].id),
        "exception": str(availability["alice"][1].id),
        "block": str(plan_blocks["alice"].id),
    }
    missing = {key: str(uuid.uuid4()) for key in hers}
    return {**hers, **mine}, {**missing, **mine}


async def snapshot(api: AsyncClient, rows: Rows, conversation: Conversation) -> tuple[Any, ...]:
    """Everything a user owns, as their own client sees it."""
    return (
        (await api.get(f"/conversations/{conversation.id}")).json(),
        (await api.get("/modules")).json(),
        (await api.get(f"/modules/{rows.module.id}/topics")).json(),
        (await api.get("/assessments")).json(),
        (await api.get("/tasks")).json(),
        (await api.get(f"/modules/{rows.module.id}/sessions")).json(),
        (await api.get(f"/sessions/{rows.study_session.id}")).json(),
        (await api.get("/sessions/active")).json(),
        (await api.get(f"/modules/{rows.module.id}/materials")).json(),
        (await api.get("/availability/rules")).json(),
        (await api.get("/availability/exceptions")).json(),
        (await api.get("/planning/settings")).json(),
        (await api.get("/plan/next")).json(),
    )


@pytest.mark.parametrize(("method", "path", "body"), ATTEMPTS)
async def test_bob_gets_the_same_404_as_for_a_missing_id(
    alice_api: AsyncClient,
    bob_api: AsyncClient,
    alice: Rows,
    bob: Rows,
    materials: dict[str, Material],
    dismissed: dict[str, TopicReview],
    conversations: dict[str, Conversation],
    availability: dict[str, tuple[AvailabilityRule, AvailabilityException]],
    plan_blocks: dict[str, PlanBlock],
    method: str,
    path: str,
    body: dict[str, Any] | None,
) -> None:
    async def snapshots() -> tuple[Any, ...]:
        return (
            await snapshot(alice_api, alice, conversations["alice"]),
            await snapshot(bob_api, bob, conversations["bob"]),
        )

    before = await snapshots()
    hers, missing = ids_of(
        alice, bob, materials, dismissed, conversations, availability, plan_blocks
    )

    attempt = await bob_api.request(method, fill(path, hers), json=fill(body, hers))
    baseline = await bob_api.request(method, fill(path, missing), json=fill(body, missing))

    assert attempt.status_code == 404
    assert (attempt.status_code, attempt.json()) == (baseline.status_code, baseline.json())
    # Neither Alice's data nor Bob's changed (a rejected write leaves nothing behind).
    assert await snapshots() == before


@pytest.mark.parametrize(
    "path",
    [
        "/assessments",
        "/assessments?status=upcoming",
        "/tasks",
        "/tasks?status=todo&status=in_progress",
    ],
)
async def test_cross_module_lists_hold_only_your_own_rows(
    alice_api: AsyncClient, bob_api: AsyncClient, alice: Rows, bob: Rows, path: str
) -> None:
    def ids(rows: list[dict[str, Any]]) -> set[str]:
        return {row["id"] for row in rows}

    his = ids((await bob_api.get(path)).json())
    hers = ids((await alice_api.get(path)).json())

    assert his == {str(bob.assessment.id)} or his == {str(bob.task.id)}
    assert hers == {str(alice.assessment.id)} or hers == {str(alice.task.id)}


async def test_planning_is_per_user(
    alice_api: AsyncClient,
    bob_api: AsyncClient,
    availability: dict[str, tuple[AvailabilityRule, AvailabilityException]],
) -> None:
    # Bob's own rule and exception only, though Alice has hers on the same day and date.
    rules = (await bob_api.get("/availability/rules")).json()
    exceptions = (await bob_api.get("/availability/exceptions")).json()
    assert [r["id"] for r in rules] == [str(availability["bob"][0].id)]
    assert [e["id"] for e in exceptions] == [str(availability["bob"][1].id)]
    # His settings change only his.
    await bob_api.patch("/planning/settings", json={"timezone": "Europe/London"})
    assert (await alice_api.get("/planning/settings")).json()["timezone"] == "Africa/Johannesburg"
    # His expanded week: his Monday rule, her unavailable date isn't his business.
    week = await bob_api.get("/availability", params={"from": "2026-11-16", "to": "2026-11-23"})
    days = week.json()["days"]
    assert days[0]["free_minutes"] == 120
    assert days[7]["source"] == "unavailable"
    await alice_api.delete(f"/availability/exceptions/{availability['alice'][1].id}")
    again = await bob_api.get("/availability", params={"from": "2026-11-23", "to": "2026-11-23"})
    assert again.json()["days"][0]["source"] == "unavailable"


async def test_lists_never_include_the_other_users_modules(
    alice_api: AsyncClient, bob_api: AsyncClient, alice: Rows, bob: Rows
) -> None:
    assert [m["id"] for m in (await alice_api.get("/modules")).json()] == [str(alice.module.id)]
    assert [m["id"] for m in (await bob_api.get("/modules")).json()] == [str(bob.module.id)]


async def test_same_code_is_fine_across_users(bob_api: AsyncClient, alice: Rows) -> None:
    # Alice already has COS330; Bob creating his own must not conflict or leak.
    response = await bob_api.post("/modules", json={"code": "COS330", "name": "Bob's"})
    assert response.status_code == 201


async def test_bob_never_sees_alices_open_session(
    alice_api: AsyncClient, bob_api: AsyncClient, alice: Rows, bob: Rows
) -> None:
    start = {"id": str(uuid.uuid4()), "occurred_at": "2026-11-01T08:00:00Z"}
    body = {"module_id": str(alice.module.id), "start": start}
    hers = (await alice_api.post("/sessions", json=body)).json()["id"]

    assert (await bob_api.get("/sessions/active")).json() is None
    history = (await bob_api.get(f"/modules/{bob.module.id}/sessions")).json()
    assert [s["id"] for s in history["items"]] == [str(bob.study_session.id)]
    assert history["total"] == 1
    summary = await bob_api.get(
        f"/modules/{bob.module.id}/sessions/summary", params={"week_start": "2026-01-01T00:00Z"}
    )
    assert summary.json()["session_count"] == 1
    # Her open session doesn't stop him starting one.
    mine = await bob_api.post("/sessions", json={"module_id": str(bob.module.id), "start": start})
    assert mine.status_code == 201
    assert mine.json()["id"] != hers


async def test_reusing_alices_event_id_neither_fails_nor_leaks(
    bob_api: AsyncClient, alice: Rows, bob: Rows
) -> None:
    # Event ids are unique per user, so a collision can't reveal that hers exists.
    start = {"id": str(alice.start_event_id), "occurred_at": "2026-11-01T08:00:00Z"}

    response = await bob_api.post(
        "/sessions", json={"module_id": str(bob.module.id), "start": start}
    )

    assert response.status_code == 201
    assert response.json()["events"][0]["id"] == str(alice.start_event_id)


async def test_bob_cannot_upload_into_alices_module(
    bob_api: AsyncClient, alice: Rows, bob: Rows, storage: LocalStorage
) -> None:
    def attempt(module_id: str) -> Any:
        return bob_api.post(
            f"/modules/{module_id}/materials",
            files={"file": ("planted.pdf", samples.pdf(1))},
            data={"kind": "slides"},
        )

    hers = await attempt(str(alice.module.id))
    baseline = await attempt(str(uuid.uuid4()))

    assert hers.status_code == 404
    assert (hers.status_code, hers.json()) == (baseline.status_code, baseline.json())
    assert (await bob_api.get(f"/modules/{bob.module.id}/materials")).json() == []
    assert not storage.root.exists() or not any(p.is_file() for p in storage.root.rglob("*"))


async def test_ai_status_counts_only_your_own_usage(
    session: AsyncSession, alice_api: AsyncClient, bob_api: AsyncClient, user_a: User
) -> None:
    for outcome in ("ok", "ok", "invalid_json", "error", "rate_limited"):
        session.add(
            AIUsage(
                user_id=user_a.id,
                provider="gemini",
                model="gemini-3.8-flash",
                role="smart",
                purpose="tutor",
                latency_ms=900,
                outcome=outcome,
            )
        )
    await session.commit()

    def flash(body: dict[str, Any]) -> dict[str, Any]:
        return next(m for m in body["models"] if m["model"] == "gemini-3.8-flash")

    hers = flash((await alice_api.get("/ai/status")).json())
    his = flash((await bob_api.get("/ai/status")).json())

    assert hers["used_today"] == 4  # a 429 was refused, so it used no quota
    assert his["used_today"] == 0


async def test_ai_ping_logs_and_budgets_only_against_the_caller(
    ping_llm: FakeLLM,
    session: AsyncSession,
    alice_api: AsyncClient,
    bob_api: AsyncClient,
    user_a: User,
    user_b: User,
) -> None:
    """POST /ai/ping takes no IDs; what it touches is usage, so its rows are the caller's.

    Alice uses up Flash's budget (two a day) with two tests; Bob's test still calls Flash.
    """
    for model in ("flash", "flash-lite", "oss-120b"):
        ping_llm.reply(model, ok("pong"), ok("pong"), ok("pong"))

    for _ in range(2):
        assert (await alice_api.post("/ai/ping")).status_code == 200
    his = (await bob_api.post("/ai/ping")).json()

    flash = next(r for r in his["results"] if r["model"] == "flash")
    assert flash["status"] == "ok"
    rows = await session.execute(
        select(AIUsage.user_id, AIUsage.model).where(AIUsage.purpose == "ping")
    )
    owners = [user for user, model in rows if model == "flash"]
    assert sorted(owners) == sorted([user_a.id, user_a.id, user_b.id])


async def test_the_plan_preview_is_per_user(
    alice_api: AsyncClient, bob_api: AsyncClient, alice: Rows, bob: Rows
) -> None:
    # Both have evenings free and an assessment on their own topic in 5 days.
    due = (datetime.now(UTC) + timedelta(days=5)).isoformat()
    for api, rows in ((alice_api, alice), (bob_api, bob)):
        for weekday in range(7):
            await api.post(
                "/availability/rules", json={"weekday": weekday, "start": "18:00", "end": "20:00"}
            )
        await api.patch(f"/assessments/{rows.assessment.id}", json={"due_at": due})
    await alice_api.patch(f"/topics/{alice.topic.id}/planning", json={"estimated_minutes": 600})

    his = (await bob_api.get("/plan/preview", params={"days": 7})).json()

    assert his["blocks"]
    assert {b["assessment_id"] for b in his["blocks"]} == {str(bob.assessment.id)}
    assert {b["topic_id"] for b in his["blocks"]} <= {str(bob.topic.id), None}
    report = his["feasibility"]
    assert [a["assessment_id"] for a in report["assessments"]] == [str(bob.assessment.id)]
    assert [t["topic_id"] for t in report["assessments"][0]["topics"]] == [str(bob.topic.id)]
    # Her 10 hours of workload aren't his: his topic has no figure, so two default blocks.
    assert report["overall"]["required_minutes"] == 100 - 50


async def test_the_stored_plan_is_per_user(
    alice_api: AsyncClient,
    bob_api: AsyncClient,
    alice: Rows,
    bob: Rows,
    plan_blocks: dict[str, PlanBlock],
    session: AsyncSession,
) -> None:
    # His plan and next block are his own, with his actions and no session of hers.
    his = (await bob_api.get("/plan")).json()
    assert [b["id"] for b in his["blocks"]] == [str(plan_blocks["bob"].id)]
    assert his["blocks"][0]["linked_session_id"] is None
    assert his["blocks"][0]["actions"] == {"start": True, "skip": True, "move": True}
    assert his["replan_pending"] is False
    assert (await bob_api.get("/plan/next")).json()["id"] == str(plan_blocks["bob"].id)
    # His re-plan writes his versions only; hers is untouched.
    before = (await alice_api.get("/plan")).json()
    await bob_api.post("/plan/replan")
    assert (await alice_api.get("/plan")).json() == before
    versions = await session.scalars(
        select(PlanVersion.number).where(PlanVersion.user_id == alice.user.id)
    )
    assert list(versions) == [1]


# --- reminders and the calendar feed (decision 0024) -------------------------------------


async def _subscribe(api: AsyncClient, name: str) -> dict[str, Any]:
    response = await api.post(
        "/push/subscriptions",
        json={
            "endpoint": f"https://push.example/{name}",
            "keys": {"p256dh": "BKey", "auth": "Auth"},
            "label": f"Edge on Windows ({name})",
        },
    )
    assert response.status_code == 201
    return dict(response.json())


async def test_push_devices_are_per_user(
    alice_api: AsyncClient, bob_api: AsyncClient, alice: Rows, bob: Rows, push_on: FakePushSender
) -> None:
    hers = await _subscribe(alice_api, "alice")
    his = await _subscribe(bob_api, "bob")

    # He lists only his own; removing hers is the same 404 as a missing id, and keeps hers.
    assert [d["id"] for d in (await bob_api.get("/push/subscriptions")).json()] == [his["id"]]
    attempt = await bob_api.delete(f"/push/subscriptions/{hers['id']}")
    baseline = await bob_api.delete(f"/push/subscriptions/{uuid.uuid4()}")
    assert attempt.status_code == 404
    assert attempt.json() == baseline.json()
    assert [d["id"] for d in (await alice_api.get("/push/subscriptions")).json()] == [hers["id"]]

    # The same endpoint saved by Bob is his own row, not a takeover of hers.
    same = await bob_api.post(
        "/push/subscriptions",
        json={
            "endpoint": "https://push.example/alice",
            "keys": {"p256dh": "BOther", "auth": "Other"},
            "label": "Bob's",
        },
    )
    assert same.status_code == 201 and same.json()["id"] != hers["id"]
    assert (await alice_api.get("/push/subscriptions")).json()[0]["label"] == (
        "Edge on Windows (alice)"
    )

    # His test push goes to his devices only.
    sent = (await bob_api.post("/push/test")).json()["devices"]
    assert {d["id"] for d in sent} == {his["id"], same.json()["id"]}
    # Sent with his keys: his row for the shared endpoint, not hers.
    assert sorted((t.endpoint, t.p256dh) for t, _, _ in push_on.sent) == [
        ("https://push.example/alice", "BOther"),
        ("https://push.example/bob", "BKey"),
    ]


async def test_calendar_feeds_are_per_user(
    alice_api: AsyncClient,
    bob_api: AsyncClient,
    alice: Rows,
    bob: Rows,
    plan_blocks: dict[str, PlanBlock],
) -> None:
    url = (await alice_api.post("/calendar/feed")).json()["url"]
    token = url.rsplit("/", 1)[-1].removesuffix(".ics")

    # Her link serves her plan only, to anyone holding it (no sign-in).
    body = (await bob_api.get(f"/calendar/{token}.ics")).text
    assert body.count("BEGIN:VEVENT") == 1
    assert "Microservices · COS330" in body
    his = (await bob_api.get("/calendar/plan.ics")).text
    assert his.count("BEGIN:VEVENT") == 1

    # He can't see, reset or delete her link: his own state says there's none.
    assert (await bob_api.get("/calendar/feed")).json()["exists"] is False
    assert (await bob_api.delete("/calendar/feed")).status_code == 404
    assert (await alice_api.get("/calendar/feed")).json()["exists"] is True
    mine = (await bob_api.post("/calendar/feed")).json()["url"]
    assert mine != url
    assert (await alice_api.get(f"/calendar/{token}.ics")).status_code == 200
