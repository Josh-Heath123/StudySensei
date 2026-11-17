"""Text from a material with allow_ai off never reaches the LLM client."""

import uuid
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.messages import system, user
from app.ai.sources import AI_OFF, chunks_for_prompt, material_pages_for_prompt
from app.models import Chunk, Material, User
from app.services.errors import Invalid, NotFound
from tests.academics.conftest import Rows, make_rows
from tests.ai.conftest import MakeClient
from tests.fakes import FakeLLM, ok
from tests.search.conftest import Page, add_material, run_jobs

SHARED = "Microservices communicate over REST."
PRIVATE = "MY OWN ASSIGNMENT ANSWER about microservices"


@pytest.fixture
async def alice(session: AsyncSession, user_a: User) -> Rows:
    return await make_rows(session, user_a)


@pytest.fixture
async def bob(session: AsyncSession, user_b: User) -> Rows:
    return await make_rows(session, user_b)


@pytest.fixture
async def materials(
    session: AsyncSession, alice: Rows, bob: Rows, tmp_path: Path
) -> tuple[Material, Material]:
    """Two indexed materials: lecture slides, and the student's own submission with AI off."""
    slides = await add_material(session, alice.user, alice.module, "Week 3", [Page(SHARED)])
    mine = await add_material(session, alice.user, alice.module, "u00000000_A1", [Page(PRIVATE)])
    mine.allow_ai = False
    await session.commit()
    await run_jobs(session, tmp_path)
    # The worker's rollbacks expired them; load them again.
    for row in (slides, mine, alice.user, alice.module, bob.user):
        await session.refresh(row)
    return slides, mine


async def chunk_ids(session: AsyncSession, *materials: Material) -> list[uuid.UUID]:
    ids = await session.scalars(
        select(Chunk.id).where(Chunk.material_id.in_([m.id for m in materials]))
    )
    return list(ids)


async def test_chunks_from_materials_with_ai_off_are_left_out(
    session: AsyncSession, alice: Rows, materials: tuple[Material, Material]
) -> None:
    slides, mine = materials
    ids = await chunk_ids(session, mine, slides)
    assert len(ids) == 2

    found = await chunks_for_prompt(session, ids, user_id=alice.user.id)

    assert [c.text for c in found] == [SHARED]
    assert found[0].material_title == "Week 3"


async def test_turning_ai_off_later_takes_effect_at_once(
    session: AsyncSession, alice: Rows, materials: tuple[Material, Material]
) -> None:
    slides, _ = materials
    ids = await chunk_ids(session, slides)
    slides.allow_ai = False
    await session.commit()

    assert await chunks_for_prompt(session, ids, user_id=alice.user.id) == []


async def test_another_users_chunks_are_left_out(
    session: AsyncSession, bob: Rows, materials: tuple[Material, Material]
) -> None:
    ids = await chunk_ids(session, *materials)

    assert await chunks_for_prompt(session, ids, user_id=bob.user.id) == []


async def test_material_pages_refuse_a_material_with_ai_off(
    session: AsyncSession, alice: Rows, bob: Rows, materials: tuple[Material, Material]
) -> None:
    slides, mine = materials

    title, pages = await material_pages_for_prompt(session, slides.id, user_id=alice.user.id)
    assert (title, [p.text for p in pages]) == ("Week 3", [SHARED])

    with pytest.raises(Invalid, match=AI_OFF):
        await material_pages_for_prompt(session, mine.id, user_id=alice.user.id)
    with pytest.raises(NotFound):
        await material_pages_for_prompt(session, slides.id, user_id=bob.user.id)


async def test_a_prompt_built_from_sources_never_carries_private_text(
    session: AsyncSession,
    alice: Rows,
    materials: tuple[Material, Material],
    make_client: MakeClient,
    fake_llm: FakeLLM,
) -> None:
    """End to end: gather every chunk in the module, prompt, and inspect what was sent."""
    every_chunk = list(
        await session.scalars(select(Chunk.id).where(Chunk.module_id == alice.module.id))
    )
    sources = await chunks_for_prompt(session, every_chunk, user_id=alice.user.id)
    context = "\n".join(
        f"[S{i}] {c.material_title} p{c.page_number}: {c.text}" for i, c in enumerate(sources, 1)
    )
    fake_llm.reply("flash", ok("They use REST [S1]."))

    await make_client().complete_text(
        "smart",
        [system("Answer from the sources."), user(f"{context}\n\nHow do services talk?")],
        purpose="tutor",
        user_id=alice.user.id,
    )

    sent = fake_llm.sent_text()
    assert SHARED in sent
    assert PRIVATE not in sent
    assert "u00000000" not in sent
    assert alice.user.email not in sent
