"""GET /modules/{id}/topic-map, POST …/build, the tree's page counts, and AI → user edits."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.kinds import EXTRACT_TOPICS, LINK_TOPICS, MERGE_TOPICS
from app.models import Job, Topic, TopicPage, TopicProposal, User
from app.services.topic_maps.linking import link_module
from tests.api.conftest import ClientFactory
from tests.fakes import FakeEmbedder
from tests.topic_maps.conftest import LITE, Module


@pytest.fixture
async def api(
    client_as: ClientFactory, session: AsyncSession, module: Module
) -> AsyncIterator[AsyncClient]:
    user = await session.get(User, module.user_id)
    assert user is not None
    async with client_as(user) as client:
        yield client


async def jobs(session: AsyncSession, kind: str) -> list[Job]:
    return list(await session.scalars(select(Job).where(Job.kind == kind).order_by(Job.created_at)))


async def test_status_counts_only_eligible_materials(api: AsyncClient, module: Module) -> None:
    response = await api.get(f"/modules/{module.module_id}/topic-map")

    assert response.status_code == 200
    # Slides and notes; not the past paper, and not the answer with AI off.
    assert response.json() == {
        "eligible": 2,
        "analysed": 0,
        "pending": 0,
        "failed": 0,
        "merging": False,
        "waiting_until": None,
        "last_error": None,
        "merged_at": None,
        "review": {"kept": 0, "renamed": 0, "merged": 0, "dismissed": 0, "unreviewed": 0},
    }


async def test_build_queues_each_unanalysed_material_once(
    api: AsyncClient, session: AsyncSession, module: Module
) -> None:
    session.add(
        TopicProposal(
            user_id=module.user_id,
            module_id=module.module_id,
            material_id=module.notes,
            provider="gemini",
            model=LITE,
            topics={"topics": []},
        )
    )
    await session.commit()

    first = await api.post(f"/modules/{module.module_id}/topic-map/build")
    again = await api.post(f"/modules/{module.module_id}/topic-map/build")

    assert first.status_code == 200
    assert (first.json()["eligible"], first.json()["analysed"], first.json()["pending"]) == (
        2,
        1,
        1,
    )
    assert again.json()["pending"] == 1
    queued = await jobs(session, EXTRACT_TOPICS)
    assert [job.payload["material_id"] for job in queued] == [str(module.slides)]
    assert await jobs(session, MERGE_TOPICS) == []


async def test_build_with_everything_analysed_just_merges(
    api: AsyncClient, session: AsyncSession, module: Module
) -> None:
    for material_id in (module.slides, module.notes):
        session.add(
            TopicProposal(
                user_id=module.user_id,
                module_id=module.module_id,
                material_id=material_id,
                provider="gemini",
                model=LITE,
                topics={"topics": []},
            )
        )
    await session.commit()

    response = await api.post(f"/modules/{module.module_id}/topic-map/build")

    assert response.json()["merging"] is True
    assert await jobs(session, EXTRACT_TOPICS) == []
    assert len(await jobs(session, MERGE_TOPICS)) == 1


async def test_status_shows_when_the_ai_is_resting_and_what_failed(
    api: AsyncClient, session: AsyncSession, module: Module
) -> None:
    await api.post(f"/modules/{module.module_id}/topic-map/build")
    slides, notes = await jobs(session, EXTRACT_TOPICS)
    back_at = datetime.now(UTC) + timedelta(hours=3)
    await session.execute(
        update(Job)
        .where(Job.id == slides.id)
        .values(run_after=back_at, last_error="AIUnavailable: rate limits")
    )
    await session.execute(
        update(Job)
        .where(Job.id == notes.id)
        .values(status="failed", finished_at=datetime.now(UTC), last_error="JobError: Bad shape.")
    )
    await session.commit()

    body = (await api.get(f"/modules/{module.module_id}/topic-map")).json()

    assert (body["pending"], body["failed"], body["last_error"]) == (1, 1, "Bad shape.")
    assert datetime.fromisoformat(body["waiting_until"]) == back_at


def a_job(module: Module, kind: str, status: str, at: datetime, error: str | None = None) -> Job:
    return Job(
        user_id=module.user_id,
        kind=kind,
        payload={"module_id": str(module.module_id), "material_id": str(module.slides)},
        status=status,
        attempts=1,
        created_at=at - timedelta(minutes=1),
        finished_at=at,
        last_error=error,
    )


async def test_a_failure_before_the_latest_successful_merge_isnt_shown(
    api: AsyncClient, session: AsyncSession, module: Module
) -> None:
    """COS330: a merge failed at 22:05, then one succeeded at 22:18; the error was stale."""
    at = datetime(2026, 11, 17, 22, 0, tzinfo=UTC)
    limit = "JobError: Stopped after 4 AI calls for the topic map without a usable answer."
    session.add_all(
        [
            a_job(module, MERGE_TOPICS, "failed", at + timedelta(minutes=5), limit),
            a_job(module, MERGE_TOPICS, "succeeded", at + timedelta(minutes=18)),
        ]
    )
    await session.commit()

    body = (await api.get(f"/modules/{module.module_id}/topic-map")).json()

    assert body["last_error"] is None
    assert datetime.fromisoformat(body["merged_at"]) == at + timedelta(minutes=18)

    # A failure after that merge is shown.
    session.add(
        a_job(module, EXTRACT_TOPICS, "failed", at + timedelta(minutes=30), "JobError: Bad shape.")
    )
    await session.commit()

    body = (await api.get(f"/modules/{module.module_id}/topic-map")).json()

    assert body["last_error"] == "Bad shape."


async def test_the_tree_shows_linked_pages_and_the_ai_source(
    api: AsyncClient, session: AsyncSession, module: Module
) -> None:
    topic = Topic(
        user_id=module.user_id,
        module_id=module.module_id,
        name="Security",
        description="Keeping accounts safe.",
        source="ai",
        position=1,
    )
    session.add(topic)
    await session.flush()
    for page in (1, 3):
        session.add(
            TopicPage(
                user_id=module.user_id,
                module_id=module.module_id,
                topic_id=topic.id,
                material_id=module.slides,
                page_number=page,
            )
        )
    await link_module(
        session,
        module.module_id,
        user_id=module.user_id,
        embedder=FakeEmbedder(),
        threshold=0.99,
        max_chunks=5,
        min_page_chars=0,
    )
    await session.commit()

    tree = (await api.get(f"/modules/{module.module_id}/topics")).json()

    by_name = {node["name"]: node for node in tree}
    assert (by_name["Security"]["source"], by_name["Security"]["linked_pages"]) == ("ai", 2)
    assert (by_name["Microservices"]["source"], by_name["Microservices"]["linked_pages"]) == (
        "user",
        0,
    )


async def an_ai_topic(session: AsyncSession, module: Module) -> Topic:
    topic = Topic(
        user_id=module.user_id,
        module_id=module.module_id,
        name="Security",
        source="ai",
        position=1,
    )
    session.add(topic)
    await session.commit()
    return topic


async def test_renaming_an_ai_topic_makes_it_the_students_and_relinks(
    api: AsyncClient, session: AsyncSession, module: Module
) -> None:
    topic = await an_ai_topic(session, module)

    response = await api.patch(f"/topics/{topic.id}", json={"name": "Keeping safe"})

    assert response.json()["source"] == "user"
    assert len(await jobs(session, LINK_TOPICS)) == 1  # the module has chunks to relink


async def test_moving_an_ai_topic_makes_it_the_students(
    api: AsyncClient, session: AsyncSession, module: Module
) -> None:
    topic = await an_ai_topic(session, module)

    response = await api.post(
        f"/topics/{topic.id}/move", json={"parent_id": str(module.topic_id), "position": 0}
    )

    assert response.json()["source"] == "user"


async def test_adding_a_topic_queues_one_relink(
    api: AsyncClient, session: AsyncSession, module: Module
) -> None:
    for name in ("Caching", "Queues"):
        response = await api.post(f"/modules/{module.module_id}/topics", json={"name": name})
        assert response.json()["source"] == "user"

    assert len(await jobs(session, LINK_TOPICS)) == 1  # the second found one already waiting


# --- per-material states and retry (the Materials tab) -----------------------------


async def test_each_eligible_material_shows_its_topic_state(
    api: AsyncClient, session: AsyncSession, module: Module
) -> None:
    session.add(
        TopicProposal(
            user_id=module.user_id,
            module_id=module.module_id,
            material_id=module.notes,
            provider="gemini",
            model=LITE,
            topics={"topics": [{"name": "Normal forms", "description": "", "pages": [1]}]},
        )
    )
    session.add(
        Job(
            user_id=module.user_id,
            kind=EXTRACT_TOPICS,
            payload={"material_id": str(module.slides), "module_id": str(module.module_id)},
            status="failed",
            attempts=3,
            finished_at=datetime.now(UTC),
            last_error="JobError: The AI's topic list didn't come out in the expected shape.",
        )
    )
    await session.commit()

    response = await api.get(f"/modules/{module.module_id}/topic-map/materials")

    assert response.status_code == 200
    states = {row["material_id"]: row for row in response.json()}
    # Not the past paper, not the material with AI off.
    assert set(states) == {str(module.slides), str(module.notes)}
    assert states[str(module.notes)] == {
        "material_id": str(module.notes),
        "state": "analysed",
        "error": None,
        "model": f"gemini/{LITE}",
        "topics": 1,
    }
    failed = states[str(module.slides)]
    assert (failed["state"], failed["error"]) == (
        "failed",
        "The AI's topic list didn't come out in the expected shape.",
    )

    retried = await api.post(f"/materials/{module.slides}/topics/retry")
    again = await api.post(f"/materials/{module.slides}/topics/retry")

    assert retried.status_code == 200
    assert retried.json()["state"] == "waiting"
    assert again.json()["state"] == "waiting"
    pending = [job for job in await jobs(session, EXTRACT_TOPICS) if job.status == "queued"]
    assert [job.payload["material_id"] for job in pending] == [str(module.slides)]  # once


async def test_retry_refuses_a_material_whose_topics_arent_found(
    api: AsyncClient, module: Module
) -> None:
    for material_id in (module.private, module.past_paper):
        response = await api.post(f"/materials/{material_id}/topics/retry")
        assert response.status_code == 422
        assert "AI allowed" in response.json()["detail"]


# --- clearing AI topics -----------------------------------------------------------


async def test_clearing_ai_topics_keeps_the_students_and_rehomes_them(
    api: AsyncClient, session: AsyncSession, module: Module
) -> None:
    def topic(name: str, source: str, parent: Topic | None = None, position: int = 0) -> Topic:
        row = Topic(
            user_id=module.user_id,
            module_id=module.module_id,
            parent_id=parent.id if parent else None,
            name=name,
            source=source,
            position=position,
        )
        session.add(row)
        return row

    security = topic("Ch2 Security", "ai", position=1)
    await session.flush()
    hashing = topic("Hashing", "ai", security, 0)
    mine = topic("My exam notes", "user", security, 1)  # the student's, under an AI topic
    edited = topic("Ch3 Networks (edited)", "user", position=2)  # was AI, then edited
    await session.flush()
    deep = topic("Salting", "user", hashing, 0)  # the student's, two AI levels down
    await session.commit()
    ids = {name: row.id for name, row in [("mine", mine), ("edited", edited), ("deep", deep)]}

    response = await api.delete(f"/modules/{module.module_id}/ai-topics")

    assert response.json() == {"deleted": 2}
    tree = (await api.get(f"/modules/{module.module_id}/topics")).json()
    assert [(n["name"], n["source"], n["position"]) for n in tree] == [
        ("Microservices", "user", 0),
        ("Ch3 Networks (edited)", "user", 1),
        # Moved up in the old tree's reading order: Salting sat under Hashing, first.
        ("Salting", "user", 2),
        ("My exam notes", "user", 3),
    ]
    assert {n["id"] for n in tree} >= {str(i) for i in ids.values()}


async def test_building_after_clearing_merges_without_reanalysing(
    api: AsyncClient, session: AsyncSession, module: Module
) -> None:
    for material_id in (module.slides, module.notes):
        session.add(
            TopicProposal(
                user_id=module.user_id,
                module_id=module.module_id,
                material_id=material_id,
                provider="gemini",
                model=LITE,
                topics={"topics": []},
            )
        )
    await session.commit()
    await api.delete(f"/modules/{module.module_id}/ai-topics")

    await api.post(f"/modules/{module.module_id}/topic-map/build")

    assert await jobs(session, EXTRACT_TOPICS) == []
    assert len(await jobs(session, MERGE_TOPICS)) == 1
