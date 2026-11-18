"""Tutor retrieval: scoping, allow_ai, one source per page, the cap, the budget and the boost."""

import uuid
from pathlib import Path

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk, ChunkTopic, Material, User
from app.schemas.academics import ModuleCreate, TopicCreate
from app.services.academics.modules import create_module
from app.services.academics.topics import create_topic
from app.services.errors import NotFound
from app.services.search.embedding import Embedder
from app.services.tutor.prompts import context_text, estimate_tokens
from app.services.tutor.retrieval import MAX_SOURCES, Retrieval, fit_budget, retrieve
from tests.academics.conftest import Rows, make_rows
from tests.fakes import FakeEmbedder
from tests.search.conftest import Page, add_material, run_jobs

QUESTION = "how does a firewall filter packets"
# Each page answers the question; the number of query words in it decides its rank.
FIREWALL = [
    "A firewall filter inspects packets at the network boundary: firewall packets.",
    "A firewall can filter packets by address and port.",
    "Firewall rules filter packets.",
    "Packets are filtered by a firewall.",
    "A firewall sits between two networks and filters.",
    "Stateless packet filters look at each packet alone.",
    "Firewalls log what they drop.",
    "Packet filters are fast.",
    "Firewalls need regular rule reviews.",
    "Filtering happens per packet.",
]
UNRELATED = "Symmetric ciphers such as AES use one shared key."
BIG = 10_000


@pytest.fixture
async def alice(session: AsyncSession, user_a: User) -> Rows:
    return await make_rows(session, user_a)


@pytest.fixture
async def bob(session: AsyncSession, user_b: User) -> Rows:
    return await make_rows(session, user_b)


async def index(session: AsyncSession, rows: Rows, tmp_path: Path) -> None:
    await run_jobs(session, tmp_path)
    # The worker's rollbacks expired them.
    await session.refresh(rows.user)
    await session.refresh(rows.module)
    await session.refresh(rows.topic)
    # Start with no topic links, so each test decides which chunks are linked.
    await session.execute(delete(ChunkTopic).where(ChunkTopic.module_id == rows.module.id))
    await session.commit()


async def ask(
    session: AsyncSession,
    rows: Rows,
    embedder: Embedder,
    *,
    question: str = QUESTION,
    topic_id: uuid.UUID | None = None,
    boost: float = 1.0,
    max_tokens: int = BIG,
    user_id: uuid.UUID | None = None,
    module_id: uuid.UUID | None = None,
) -> Retrieval:
    """Retrieval as the rows' user in their module, unless other IDs are given."""
    return await retrieve(
        session,
        module_id or rows.module.id,
        question,
        user_id=user_id or rows.user.id,
        embedder=embedder,
        topic_id=topic_id,
        boost=boost,
        max_tokens=max_tokens,
    )


async def one_page_each(session: AsyncSession, rows: Rows, texts: list[str]) -> list[uuid.UUID]:
    """One single-page material per text, "Deck 1", "Deck 2"…; their IDs."""
    return [
        (await add_material(session, rows.user, rows.module, f"Deck {n}", [Page(text)])).id
        for n, text in enumerate(texts, start=1)
    ]


# --- scoping ---


async def test_another_users_module_is_not_found(
    session: AsyncSession, alice: Rows, bob: Rows, tmp_path: Path, fake_embedder: FakeEmbedder
) -> None:
    await one_page_each(session, alice, FIREWALL[:1])
    await index(session, alice, tmp_path)
    await session.refresh(bob.user)

    with pytest.raises(NotFound):
        await ask(session, alice, fake_embedder, user_id=bob.user.id)
    # Alice's own module still answers.
    assert len((await ask(session, alice, fake_embedder)).sources) == 1


async def test_another_users_topic_is_not_found(
    session: AsyncSession, alice: Rows, bob: Rows, tmp_path: Path, fake_embedder: FakeEmbedder
) -> None:
    await one_page_each(session, alice, FIREWALL[:1])
    await index(session, alice, tmp_path)
    await session.refresh(bob.topic)

    with pytest.raises(NotFound):
        await ask(session, alice, fake_embedder, topic_id=bob.topic.id, boost=2.0)


async def test_a_topic_from_another_of_the_users_modules_is_not_found(
    session: AsyncSession, alice: Rows, tmp_path: Path, fake_embedder: FakeEmbedder
) -> None:
    await one_page_each(session, alice, FIREWALL[:1])
    await index(session, alice, tmp_path)
    other = await create_module(
        session, ModuleCreate(code="COS301", name="Other"), user_id=alice.user.id
    )
    elsewhere = await create_topic(
        session, other.id, TopicCreate(name="Elsewhere"), user_id=alice.user.id
    )

    with pytest.raises(NotFound):
        await ask(session, alice, fake_embedder, topic_id=elsewhere.id, boost=2.0)


async def test_other_users_chunks_never_come_back(
    session: AsyncSession, alice: Rows, bob: Rows, tmp_path: Path, fake_embedder: FakeEmbedder
) -> None:
    await one_page_each(session, alice, FIREWALL[:2])
    await add_material(session, bob.user, bob.module, "Bob's deck", [Page(FIREWALL[0])])
    await index(session, alice, tmp_path)

    found = await ask(session, alice, fake_embedder)

    assert {s.material_title for s in found.sources} == {"Deck 1", "Deck 2"}


# --- what's kept ---


async def test_materials_with_ai_off_are_left_out(
    session: AsyncSession, alice: Rows, tmp_path: Path, fake_embedder: FakeEmbedder
) -> None:
    best_id, _ = await one_page_each(session, alice, FIREWALL[:2])
    best = await session.get(Material, best_id)
    assert best is not None
    best.allow_ai = False
    await session.commit()
    await index(session, alice, tmp_path)

    found = await ask(session, alice, fake_embedder)

    assert [s.material_title for s in found.sources] == ["Deck 2"]
    assert found.sources[0].label == "S1"


async def test_one_source_per_page_and_its_best_chunk_wins(
    session: AsyncSession, alice: Rows, tmp_path: Path, fake_embedder: FakeEmbedder
) -> None:
    # A long page splits into several chunks; only its first paragraph matches strongly.
    filler = " ".join(["Unrelated words about something else entirely."] * 60)
    long_page = f"{FIREWALL[0]}\n\n{filler}\n\n{FIREWALL[6]}"
    deck_id = (await add_material(session, alice.user, alice.module, "Long", [Page(long_page)])).id
    await one_page_each(session, alice, FIREWALL[1:3])
    await index(session, alice, tmp_path)
    chunks = list(await session.scalars(select(Chunk.text).where(Chunk.material_id == deck_id)))
    assert len(chunks) > 1

    found = await ask(session, alice, fake_embedder)

    pages = [(s.material_id, s.page_number) for s in found.sources]
    assert len(pages) == len(set(pages)) == 3
    long_source = next(s for s in found.sources if s.material_title == "Long")
    assert long_source.text.startswith(FIREWALL[0])


async def test_at_most_eight_sources_labelled_in_rank_order(
    session: AsyncSession, alice: Rows, tmp_path: Path, fake_embedder: FakeEmbedder
) -> None:
    await one_page_each(session, alice, FIREWALL)
    await index(session, alice, tmp_path)

    found = await ask(session, alice, fake_embedder)

    assert len(found.sources) == MAX_SOURCES
    assert [s.label for s in found.sources] == [f"S{n}" for n in range(1, 9)]
    scores = [s.score for s in found.sources]
    assert scores == sorted(scores, reverse=True)
    assert found.sources[0].material_title == "Deck 1"
    assert found.dropped == 0


async def test_each_source_says_where_it_is_from(
    session: AsyncSession, alice: Rows, tmp_path: Path, fake_embedder: FakeEmbedder
) -> None:
    deck_id = (
        await add_material(
            session,
            alice.user,
            alice.module,
            "CH09",
            [Page(UNRELATED), Page(FIREWALL[0], title="Types of firewalls")],
        )
    ).id
    await index(session, alice, tmp_path)

    top = (await ask(session, alice, fake_embedder)).sources[0]

    assert (top.material_id, top.material_title, top.page_number, top.page_title) == (
        deck_id,
        "CH09",
        2,
        "Types of firewalls",
    )
    assert top.text == FIREWALL[0]
    assert top.vector_rank == 1 and top.keyword_rank == 1
    assert top.score == top.search_score == pytest.approx(2 / 61)


async def test_no_question_or_no_index_gives_no_sources(
    session: AsyncSession, alice: Rows, tmp_path: Path, fake_embedder: FakeEmbedder
) -> None:
    assert (await ask(session, alice, fake_embedder)).sources == []
    await one_page_each(session, alice, FIREWALL[:1])
    await index(session, alice, tmp_path)

    empty = await ask(session, alice, fake_embedder, question="   ")
    assert (empty.sources, empty.context_tokens) == ([], 0)


# --- the token budget ---


async def test_the_budget_drops_the_lowest_ranked_sources_first(
    session: AsyncSession, alice: Rows, tmp_path: Path, fake_embedder: FakeEmbedder
) -> None:
    await one_page_each(session, alice, FIREWALL)
    await index(session, alice, tmp_path)
    three = (await ask(session, alice, fake_embedder)).sources[:3]
    # Exactly what the top three cost, so the fourth doesn't fit.
    budget = estimate_tokens(context_text([s.for_prompt() for s in three]))

    cut = await ask(session, alice, fake_embedder, max_tokens=budget)

    assert [s.chunk_id for s in cut.sources] == [s.chunk_id for s in three]
    assert [s.label for s in cut.sources] == ["S1", "S2", "S3"]
    assert cut.context_tokens <= budget
    assert cut.dropped == MAX_SOURCES - 3
    # Never cut in half: each kept passage is whole.
    assert [s.text for s in cut.sources] == [s.text for s in three]


async def test_a_budget_too_small_for_any_source_gives_none(
    session: AsyncSession, alice: Rows, tmp_path: Path, fake_embedder: FakeEmbedder
) -> None:
    await one_page_each(session, alice, FIREWALL[:2])
    await index(session, alice, tmp_path)

    found = await ask(session, alice, fake_embedder, max_tokens=5)

    assert (found.sources, found.context_tokens, found.dropped) == ([], 0, 2)


def test_fit_budget_drops_from_the_end() -> None:
    sizes = [5, 1, 4, 2]
    assert fit_budget(sizes, sum, 10) == [5, 1, 4]
    assert fit_budget(sizes, sum, 6) == [5, 1]
    assert fit_budget(sizes, sum, 4) == []
    assert fit_budget(sizes, sum, 12) == sizes


# --- the topic boost ---


async def link(
    session: AsyncSession, module_id: uuid.UUID, material_id: uuid.UUID, topic_id: uuid.UUID
) -> None:
    """Link the material's one chunk to the topic."""
    chunk_id = (
        await session.scalars(select(Chunk.id).where(Chunk.material_id == material_id))
    ).one()
    session.add(
        ChunkTopic(
            module_id=module_id,
            chunk_id=chunk_id,
            topic_id=topic_id,
            score=0.8,
            method="similarity",
        )
    )
    await session.commit()


async def decks_and_topics(
    session: AsyncSession, rows: Rows, tmp_path: Path, count: int
) -> tuple[list[uuid.UUID], uuid.UUID, uuid.UUID, uuid.UUID]:
    """Indexed one-page decks, and the session's topic, a subtopic of it and an unrelated one."""
    decks = await one_page_each(session, rows, FIREWALL[:count])
    await index(session, rows, tmp_path)
    module_id, topic_id, user_id = rows.module.id, rows.topic.id, rows.user.id
    sub = await create_topic(
        session, module_id, TopicCreate(name="Packet filters", parent_id=topic_id), user_id=user_id
    )
    sub_id = sub.id
    other = await create_topic(session, module_id, TopicCreate(name="Ciphers"), user_id=user_id)
    return decks, topic_id, sub_id, other.id


def order(found: Retrieval) -> list[str]:
    return [s.material_title for s in found.sources]


async def test_the_boost_lifts_only_chunks_linked_to_the_topic_or_its_subtopics(
    session: AsyncSession, alice: Rows, tmp_path: Path, fake_embedder: FakeEmbedder
) -> None:
    module_id, user_id = alice.module.id, alice.user.id
    decks, topic_id, sub_id, other_id = await decks_and_topics(session, alice, tmp_path, 6)
    plain = await ask(session, alice, fake_embedder, user_id=user_id, module_id=module_id)
    last, second = plain.sources[-1], plain.sources[1]
    # The last-ranked page is linked to a subtopic of the session's topic; the second to an
    # unrelated topic.
    await link(session, module_id, last.material_id, sub_id)
    await link(session, module_id, second.material_id, other_id)

    boosted = await ask(
        session,
        alice,
        fake_embedder,
        user_id=user_id,
        module_id=module_id,
        topic_id=topic_id,
        boost=10.0,
    )

    assert not any(s.boosted for s in plain.sources)
    assert all(s.score == s.search_score for s in plain.sources)
    top = boosted.sources[0]
    assert (top.chunk_id, top.label, top.boosted) == (last.chunk_id, "S1", True)
    assert top.score == pytest.approx(last.search_score * 10.0)
    rest = boosted.sources[1:]
    assert not any(s.boosted for s in rest)
    assert all(s.score == s.search_score for s in rest)
    # The others keep their order, the one linked to the unrelated topic included.
    assert order(boosted)[1:] == order(plain)[:-1]
    assert len(decks) == 6


async def test_no_topic_means_no_boost(
    session: AsyncSession, alice: Rows, tmp_path: Path, fake_embedder: FakeEmbedder
) -> None:
    module_id, user_id = alice.module.id, alice.user.id
    _, topic_id, _, _ = await decks_and_topics(session, alice, tmp_path, 3)
    plain = await ask(session, alice, fake_embedder, user_id=user_id, module_id=module_id)
    await link(session, module_id, plain.sources[-1].material_id, topic_id)

    found = await ask(
        session, alice, fake_embedder, user_id=user_id, module_id=module_id, boost=10.0
    )

    assert order(found) == order(plain)
    assert not any(s.boosted for s in found.sources)


async def test_a_boost_of_one_changes_nothing(
    session: AsyncSession, alice: Rows, tmp_path: Path, fake_embedder: FakeEmbedder
) -> None:
    module_id, user_id = alice.module.id, alice.user.id
    _, topic_id, _, _ = await decks_and_topics(session, alice, tmp_path, 3)
    plain = await ask(session, alice, fake_embedder, user_id=user_id, module_id=module_id)
    await link(session, module_id, plain.sources[-1].material_id, topic_id)

    found = await ask(
        session,
        alice,
        fake_embedder,
        user_id=user_id,
        module_id=module_id,
        topic_id=topic_id,
        boost=1.0,
    )

    assert order(found) == order(plain)
    assert found.sources[-1].boosted
    assert all(s.score == s.search_score for s in found.sources)


async def test_a_topic_with_no_linked_chunks_boosts_nothing(
    session: AsyncSession, alice: Rows, tmp_path: Path, fake_embedder: FakeEmbedder
) -> None:
    module_id, user_id = alice.module.id, alice.user.id
    _, topic_id, _, _ = await decks_and_topics(session, alice, tmp_path, 3)
    plain = await ask(session, alice, fake_embedder, user_id=user_id, module_id=module_id)

    found = await ask(
        session,
        alice,
        fake_embedder,
        user_id=user_id,
        module_id=module_id,
        topic_id=topic_id,
        boost=10.0,
    )

    assert order(found) == order(plain)
    assert not any(s.boosted for s in found.sources)
