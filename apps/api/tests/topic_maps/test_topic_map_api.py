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
