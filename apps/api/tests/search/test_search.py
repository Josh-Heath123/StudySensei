"""Hybrid search over a module's chunks, with the fake embedder (bag of words)."""

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.schemas.academics import ModuleCreate
from app.services.academics.modules import create_module
from app.services.errors import NotFound
from app.services.search.search import SearchResults, SnippetPart, search_module
from tests.academics.conftest import Rows
from tests.fakes import FakeEmbedder
from tests.search.conftest import Page, add_material, run_jobs

AUTH = "Passwords are salted and hashed with bcrypt before they are stored."
SESSIONS = "Session tokens expire after thirty minutes of inactivity."
CRYPTO = "Symmetric ciphers such as AES use one shared key."


@pytest.fixture
async def indexed(session: AsyncSession, alice: Rows, tmp_path: Path) -> Rows:
    """Alice's module: two decks, indexed."""
    await add_material(
        session,
        alice.user,
        alice.module,
        "CH03",
        [Page(AUTH, title="User authentication"), Page(SESSIONS, title="Sessions")],
    )
    await add_material(session, alice.user, alice.module, "CH05", [Page(CRYPTO)])
    await run_jobs(session, tmp_path)
    await session.refresh(alice.user)
    await session.refresh(alice.module)
    return alice


async def search(
    session: AsyncSession, rows: Rows, query: str, embedder: FakeEmbedder, limit: int = 8
) -> SearchResults:
    return await search_module(
        session, rows.module.id, query, user_id=rows.user.id, embedder=embedder, limit=limit
    )


async def test_an_exact_phrase_ranks_its_page_first(
    session: AsyncSession, indexed: Rows, fake_embedder: FakeEmbedder
) -> None:
    fake_embedder.query_calls.clear()  # indexing's topic links embedded topic names
    found = await search(session, indexed, "salted passwords bcrypt", fake_embedder)

    assert found.indexed_chunks == 3
    top = found.hits[0]
    assert (top.material_title, top.original_filename, top.page_number, top.page_title) == (
        "CH03",
        "CH03.pdf",
        1,
        "User authentication",
    )
    assert (top.text, top.position) == (AUTH, 0)
    assert (top.vector_rank, top.keyword_rank) == (1, 1)
    assert top.score == pytest.approx(2 / 61)
    assert SnippetPart("Passwords", True) in top.snippet
    assert SnippetPart("salted", True) in top.snippet
    assert AUTH.startswith("".join(part.text for part in top.snippet))
    assert fake_embedder.query_calls == ["salted passwords bcrypt"]


async def test_scores_are_best_first_and_fused_from_both_rankings(
    session: AsyncSession, indexed: Rows, fake_embedder: FakeEmbedder
) -> None:
    found = await search(session, indexed, "session tokens", fake_embedder)
    scores = [hit.score for hit in found.hits]
    assert scores == sorted(scores, reverse=True)
    assert found.hits[0].text == SESSIONS
    # Every chunk is somewhere in the vector ranking; only the match is in the keyword one.
    assert all(hit.vector_rank is not None for hit in found.hits)
    assert [hit.keyword_rank for hit in found.hits] == [1, None, None]


async def test_a_query_with_no_word_matches_still_finds_by_meaning(
    session: AsyncSession, indexed: Rows, fake_embedder: FakeEmbedder
) -> None:
    found = await search(session, indexed, "the of and", fake_embedder)  # stop words only
    assert len(found.hits) == 3
    assert all(hit.keyword_rank is None for hit in found.hits)
    # No highlights: the snippet is the start of the text.
    assert all(not any(part.highlight for part in hit.snippet) for hit in found.hits)


async def test_websearch_syntax_works(
    session: AsyncSession, indexed: Rows, fake_embedder: FakeEmbedder
) -> None:
    found = await search(session, indexed, '"shared key" -bcrypt', fake_embedder)
    assert found.hits[0].text == CRYPTO
    assert found.hits[0].keyword_rank == 1


async def test_limit_caps_the_results(
    session: AsyncSession, indexed: Rows, fake_embedder: FakeEmbedder
) -> None:
    found = await search(session, indexed, "passwords", fake_embedder, limit=1)
    assert [hit.text for hit in found.hits] == [AUTH]


async def test_nothing_indexed_says_so_without_embedding_the_query(
    session: AsyncSession, alice: Rows, fake_embedder: FakeEmbedder
) -> None:
    found = await search(session, alice, "passwords", fake_embedder)
    assert (found.hits, found.indexed_chunks) == ([], 0)
    assert fake_embedder.query_calls == []


async def test_a_blank_query_returns_nothing(
    session: AsyncSession, indexed: Rows, fake_embedder: FakeEmbedder
) -> None:
    found = await search(session, indexed, "   ", fake_embedder)
    assert (found.hits, found.indexed_chunks) == ([], 3)


async def test_only_this_modules_chunks_are_searched(
    session: AsyncSession,
    indexed: Rows,
    bob: Rows,
    user_b: User,
    tmp_path: Path,
    fake_embedder: FakeEmbedder,
) -> None:
    alice_id = indexed.user.id
    other = await create_module(
        session, ModuleCreate(code="COS301", name="Other"), user_id=alice_id
    )
    await session.refresh(indexed.user)
    await add_material(session, indexed.user, other, "Other", [Page(AUTH)])
    await add_material(session, user_b, bob.module, "Bobs", [Page(AUTH)])
    await run_jobs(session, tmp_path)
    for row in (indexed.user, indexed.module, bob.user, bob.module):
        await session.refresh(row)

    found = await search(session, indexed, "salted passwords bcrypt", fake_embedder)
    assert found.indexed_chunks == 3
    assert {hit.material_title for hit in found.hits} == {"CH03", "CH05"}

    bobs = await search(session, bob, "salted passwords bcrypt", fake_embedder)
    assert [hit.material_title for hit in bobs.hits] == ["Bobs"]


async def test_another_users_module_is_not_found(
    session: AsyncSession, indexed: Rows, bob: Rows, fake_embedder: FakeEmbedder
) -> None:
    with pytest.raises(NotFound):
        await search_module(
            session, indexed.module.id, "passwords", user_id=bob.user.id, embedder=fake_embedder
        )
