"""Near-empty pages (title slides, chapter dividers, captions) aren't similarity candidates.

Cited pages still link whatever their length, and the relink that migration 0015 queues
keeps the student's unlinks and the cited links.
"""

import importlib.util
import uuid
from pathlib import Path
from types import ModuleType

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.jobs import queue
from app.jobs.kinds import LINK_TOPICS, MERGE_TOPICS
from app.models import Chunk, ChunkTopic, Job, Module, Topic, TopicPage, TopicUnlink, User
from app.services.topic_maps.linking import link_module
from tests.academics.conftest import make_rows
from tests.fakes import FakeEmbedder
from tests.search.conftest import Page, add_material, run_jobs
from tests.topic_maps.conftest import Module as IndexedModule

# Under 150 characters, like COS330's deck title slide and "Chapter N" dividers.
TITLE = "Buffer overflow attacks"
DIVIDER = "Stack smashing"
# Over 150 characters each: pages that teach.
OVERFLOW = (
    "A buffer overflow attack writes past the end of a fixed-size stack buffer, overwriting "
    "the saved return address so that the function returns into code the attacker chose."
)
SMASHING = (
    "Stack smashing overwrites the return address on the stack. Canaries, non-executable "
    "stacks and address space layout randomisation make stack smashing much harder to exploit."
)
SMASHING_AGAIN = SMASHING + " The same defences appear again in the summary slide."


async def add_chapter(session: AsyncSession, module: IndexedModule, tmp_path: Path) -> uuid.UUID:
    """A slide deck: title (1), overflow (2), smashing (3, 4), divider (5); indexed."""
    user = await session.get(User, module.user_id)
    row = await session.get(Module, module.module_id)
    assert user is not None and row is not None
    deck = await add_material(
        session,
        user,
        row,
        "Chapter 10",
        [Page(TITLE), Page(OVERFLOW), Page(SMASHING), Page(SMASHING_AGAIN), Page(DIVIDER)],
    )
    deck_id = deck.id
    await run_jobs(session, tmp_path)
    await session.execute(delete(Job).where(Job.user_id == module.user_id))
    await session.commit()
    return deck_id


async def a_topic(
    session: AsyncSession, module: IndexedModule, name: str, description: str, source: str
) -> uuid.UUID:
    topic = Topic(
        user_id=module.user_id,
        module_id=module.module_id,
        name=name,
        description=description,
        source=source,
        position=9,
    )
    session.add(topic)
    await session.commit()
    return topic.id


async def linked_pages(
    session: AsyncSession, topic_id: uuid.UUID, material_id: uuid.UUID
) -> dict[int, str]:
    rows = await session.execute(
        select(Chunk.page_number, ChunkTopic.method)
        .join(Chunk, Chunk.id == ChunkTopic.chunk_id)
        .where(ChunkTopic.topic_id == topic_id, Chunk.material_id == material_id)
    )
    return {page: method for page, method in rows}


async def link(session: AsyncSession, module: IndexedModule, min_page_chars: int) -> None:
    await link_module(
        session,
        module.module_id,
        user_id=module.user_id,
        embedder=FakeEmbedder(),
        threshold=0.3,
        max_chunks=12,
        min_page_chars=min_page_chars,
    )
    await session.commit()


def test_the_default_minimum_is_150_characters() -> None:
    assert get_settings().topic_link_min_page_chars == 150
    assert len(TITLE) < 150 and len(DIVIDER) < 150
    assert len(OVERFLOW) >= 150 and len(SMASHING) >= 150


async def test_a_near_empty_page_with_a_high_score_is_not_linked(
    session: AsyncSession, module: IndexedModule, tmp_path: Path
) -> None:
    deck = await add_chapter(session, module, tmp_path)
    topic = await a_topic(session, module, "Buffer overflow attacks", OVERFLOW, "ai")

    # With no minimum the title slide matches the topic name and links by similarity.
    await link(session, module, min_page_chars=0)
    assert (await linked_pages(session, topic, deck)).get(1) == "similarity"

    await link(session, module, min_page_chars=150)

    pages = await linked_pages(session, topic, deck)
    assert 1 not in pages and 5 not in pages
    assert pages[2] == "similarity"


async def test_a_cited_near_empty_page_stays_linked(
    session: AsyncSession, module: IndexedModule, tmp_path: Path
) -> None:
    deck = await add_chapter(session, module, tmp_path)
    topic = await a_topic(session, module, "Buffer overflow attacks", OVERFLOW, "ai")
    session.add(
        TopicPage(
            user_id=module.user_id,
            module_id=module.module_id,
            topic_id=topic,
            material_id=deck,
            page_number=1,
        )
    )
    await session.commit()

    await link(session, module, min_page_chars=150)

    assert (await linked_pages(session, topic, deck))[1] == "pages"


async def test_the_relink_job_keeps_unlinks_and_cited_links(
    session: AsyncSession, module: IndexedModule, tmp_path: Path
) -> None:
    deck = await add_chapter(session, module, tmp_path)
    ai_topic = await a_topic(session, module, "Buffer overflow attacks", OVERFLOW, "ai")
    mine = await a_topic(session, module, "Stack smashing", SMASHING, "user")
    session.add_all(
        [
            # The AI cited the title slide (a figure slide would be the same).
            TopicPage(
                user_id=module.user_id,
                module_id=module.module_id,
                topic_id=ai_topic,
                material_id=deck,
                page_number=1,
            ),
            # The student unlinked page 3 from their own topic.
            TopicUnlink(
                user_id=module.user_id,
                module_id=module.module_id,
                topic_id=mine,
                material_id=deck,
                page_number=3,
            ),
        ]
    )
    await session.commit()
    # The links as they were before 0015: the divider linked by similarity.
    await link(session, module, min_page_chars=0)
    assert (await linked_pages(session, mine, deck)).get(5) == "similarity"

    # As queued by migration 0015, run by the worker with the real settings.
    queue.enqueue(
        session, LINK_TOPICS, {"module_id": str(module.module_id)}, user_id=module.user_id
    )
    await session.commit()
    assert await run_jobs(session, tmp_path) == 1

    ai_pages = await linked_pages(session, ai_topic, deck)
    assert ai_pages[1] == "pages"  # cited: unchanged
    my_pages = await linked_pages(session, mine, deck)
    assert 3 not in my_pages  # unlinked: stays unlinked
    assert 5 not in my_pages  # the divider is gone
    assert my_pages[4] == "similarity"  # the student's own topic gets similarity links


# --- migration 0015 ---

PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "0015_relink_without_near_empty_pages.py"
)


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0015", PATH)
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


async def test_the_migration_queues_one_link_job_per_module_with_a_topic_map(
    session: AsyncSession, module: IndexedModule, user_b: User
) -> None:
    # Alice's module has chunk links: a topic citing a page.
    session.add(
        TopicPage(
            user_id=module.user_id,
            module_id=module.module_id,
            topic_id=module.topic_id,
            material_id=module.slides,
            page_number=1,
        )
    )
    await session.commit()
    await link(session, module, min_page_chars=0)
    merged = await make_rows(session, user_b)  # a merge succeeded
    waiting = await make_rows(session, user_b, code="COS111")  # merged, relink already queued
    bare = await make_rows(session, user_b, code="COS000")  # no topic map
    for rows in (merged, waiting):
        session.add(
            Job(
                user_id=rows.user.id,
                kind=MERGE_TOPICS,
                status="succeeded",
                payload={"module_id": str(rows.module.id)},
            )
        )
    session.add(
        Job(user_id=user_b.id, kind=LINK_TOPICS, payload={"module_id": str(waiting.module.id)})
    )
    await session.flush()

    def run(sync_connection: object) -> None:
        context = MigrationContext.configure(sync_connection)  # type: ignore[arg-type]
        with Operations.context(context):
            load().queue_relinking()

    await (await session.connection()).run_sync(run)

    jobs = [
        tuple(row)
        for row in await session.execute(
            select(Job.user_id, Job.payload["module_id"].astext).where(
                Job.kind == LINK_TOPICS, Job.status == "queued"
            )
        )
    ]
    assert sorted(jobs) == sorted(
        [
            (module.user_id, str(module.module_id)),
            (user_b.id, str(merged.module.id)),
            (user_b.id, str(waiting.module.id)),  # the one already queued, not a second
        ]
    )
    assert str(bare.module.id) not in {str(p) for _, p in jobs}
