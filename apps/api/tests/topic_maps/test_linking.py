"""Chunk ↔ topic links: by cited pages and by meaning, rebuilt from scratch, cascading."""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk, ChunkTopic, Material, Topic, TopicPage
from app.services.topic_maps.linking import link_module, linked_page_counts
from tests.fakes import FakeEmbedder
from tests.topic_maps.conftest import AUTH, NORMAL_FORMS, SESSIONS, Module


async def a_topic(
    session: AsyncSession, module: Module, name: str, description: str | None = None
) -> uuid.UUID:
    topic = Topic(
        user_id=module.user_id,
        module_id=module.module_id,
        name=name,
        description=description,
        source="ai",
        position=9,
    )
    session.add(topic)
    await session.commit()
    return topic.id


async def cite(session: AsyncSession, module: Module, topic_id: uuid.UUID, page: int) -> None:
    session.add(
        TopicPage(
            user_id=module.user_id,
            module_id=module.module_id,
            topic_id=topic_id,
            material_id=module.slides,
            page_number=page,
        )
    )
    await session.commit()


async def link(session: AsyncSession, module: Module, threshold: float = 0.5) -> int:
    count = await link_module(
        session,
        module.module_id,
        user_id=module.user_id,
        embedder=FakeEmbedder(),
        threshold=threshold,
        max_chunks=5,
    )
    await session.commit()
    return count


async def links(session: AsyncSession, topic_id: uuid.UUID) -> list[tuple[str, str, float]]:
    rows = await session.execute(
        select(Chunk.text, ChunkTopic.method, ChunkTopic.score)
        .join(Chunk, Chunk.id == ChunkTopic.chunk_id)
        .where(ChunkTopic.topic_id == topic_id)
        .order_by(Chunk.text)
    )
    return [(text, method, round(score, 2)) for text, method, score in rows]


async def test_cited_pages_link_their_chunks(session: AsyncSession, module: Module) -> None:
    topic = await a_topic(session, module, "Keeping accounts safe")
    await cite(session, module, topic, 1)

    await link(session, module, threshold=0.99)

    assert await links(session, topic) == [(AUTH, "pages", 1.0)]


async def test_similar_chunks_link_above_the_threshold(
    session: AsyncSession, module: Module
) -> None:
    topic = await a_topic(
        session, module, "Normal form", "Third normal form removes transitive dependencies."
    )

    await link(session, module)

    found = await links(session, topic)
    assert [(text, method) for text, method, _ in found] == [(NORMAL_FORMS, "similarity")]
    assert 0.5 <= found[0][2] <= 1.0
    # Nothing similar enough elsewhere in the module.
    assert all(text not in (AUTH, SESSIONS) for text, _, _ in found)


async def test_a_chunk_linked_both_ways_keeps_pages(session: AsyncSession, module: Module) -> None:
    topic = await a_topic(session, module, "Sessions", SESSIONS)
    await cite(session, module, topic, 3)

    await link(session, module)

    assert await links(session, topic) == [(SESSIONS, "pages", 1.0)]


async def test_links_are_rebuilt_from_scratch(session: AsyncSession, module: Module) -> None:
    topic = await a_topic(session, module, "Session tokens", SESSIONS)
    await link(session, module)
    assert [text for text, _, _ in await links(session, topic)] == [SESSIONS]

    renamed = await session.get(Topic, topic)
    assert renamed is not None
    renamed.name, renamed.description = "Normal form", "Third normal form, transitive dependencies."
    await session.commit()
    await link(session, module)

    assert [text for text, _, _ in await links(session, topic)] == [NORMAL_FORMS]


async def test_deleting_a_topic_or_a_material_removes_its_links(
    session: AsyncSession, module: Module
) -> None:
    keep = await a_topic(session, module, "Normal form", NORMAL_FORMS)
    gone = await a_topic(session, module, "Sessions", SESSIONS)
    await cite(session, module, gone, 1)
    await link(session, module)
    assert await links(session, gone) and await links(session, keep)

    await session.execute(delete(Topic).where(Topic.id == gone))
    await session.execute(delete(Material).where(Material.id == module.notes))
    await session.commit()

    remaining = await session.scalars(select(ChunkTopic.topic_id))
    assert list(remaining) == []


async def test_linked_pages_count_distinct_pages_per_topic(
    session: AsyncSession, module: Module
) -> None:
    topic = await a_topic(session, module, "Security")
    for page in (1, 3):
        await cite(session, module, topic, page)
    await link(session, module, threshold=0.99)

    counts = await linked_page_counts(session, module.module_id, user_id=module.user_id)

    assert counts == {topic: 2}
    other_user = uuid.uuid4()
    assert await linked_page_counts(session, module.module_id, user_id=other_user) == {}
