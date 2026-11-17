import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LLMClient, set_llm_client
from app.models import Job, Material, User
from tests.academics.conftest import make_rows
from tests.ai.conftest import (  # noqa: F401 (fixtures shared with the AI client tests)
    MakeClient,
    fake_llm,
    make_client,
    settings,
    sleeps,
    usage_sessions,
)
from tests.api.conftest import client_as  # noqa: F401 (HTTP clients acting as a user)
from tests.fakes import ok
from tests.search.conftest import Page, add_material, run_jobs

# The test client's "long" role: Flash-Lite first, then Groq (tests/ai/conftest.py).
LITE = "flash-lite"

AUTH = "Passwords are salted and hashed with bcrypt before they are stored."
SESSIONS = "Session tokens expire after thirty minutes of inactivity."
NORMAL_FORMS = "Third normal form removes transitive dependencies between attributes."
PRIVATE = "MY OWN ANSWER: the system uses microservices for every component."


@dataclass
class Module:
    """IDs only: the worker's rollbacks expire ORM objects."""

    user_id: uuid.UUID
    module_id: uuid.UUID
    topic_id: uuid.UUID
    slides: uuid.UUID
    notes: uuid.UUID
    past_paper: uuid.UUID
    private: uuid.UUID


@pytest.fixture
async def module(session: AsyncSession, user_a: User, tmp_path: Path) -> Module:
    """An indexed module: slides (one scanned page), notes, a past paper, and the student's
    own answer with AI off. It has one user topic, "Microservices". No jobs are left."""
    user_id = user_a.id  # the worker's rollbacks expire user_a
    rows = await make_rows(session, user_a)
    module_id, topic_id = rows.module.id, rows.topic.id
    slides = await add_material(
        session,
        rows.user,
        rows.module,
        "Week 1 Security",
        [Page(AUTH, title="Passwords"), Page("", scanned=True), Page(SESSIONS, title="Sessions")],
    )
    notes = await add_material(session, rows.user, rows.module, "Databases", [Page(NORMAL_FORMS)])
    notes.kind = "notes"
    paper = await add_material(session, rows.user, rows.module, "Exam 2024", [Page("Q1 ...")])
    paper.kind = "past_paper"
    private = await add_material(session, rows.user, rows.module, "u00000000 A1", [Page(PRIVATE)])
    private.allow_ai = False
    await session.commit()
    ids = (slides.id, notes.id, paper.id, private.id)
    await run_jobs(session, tmp_path)
    # Indexing queued topic jobs, which ran without AI; start each test from a clean queue.
    await session.execute(delete(Job).where(Job.user_id == user_id))
    await session.commit()
    return Module(user_id, module_id, topic_id, *ids)


@pytest.fixture
def client(make_client: MakeClient) -> Iterator[LLMClient]:  # noqa: F811
    """The process's LLM client, on the fake transport (jobs call get_llm_client())."""
    llm = make_client()
    set_llm_client(llm)
    yield llm
    set_llm_client(None)


def topics_reply(*topics: dict[str, Any]) -> Any:
    return ok(json.dumps({"topics": list(topics)}))


def node(name: str, pages: list[int] | None = None, **extra: Any) -> dict[str, Any]:
    return {"name": name, "description": f"About {name.lower()}.", "pages": pages or [], **extra}


async def material(session: AsyncSession, material_id: uuid.UUID) -> Material:
    found = await session.get(Material, material_id, populate_existing=True)
    assert found is not None
    return found
