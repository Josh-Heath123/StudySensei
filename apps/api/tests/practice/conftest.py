"""A module with a chapter, its subtopic and another topic, and passages linked to them from
materials of every kind and both AI settings (ADR 0025)."""

import hashlib
import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LLMClient, set_llm_client
from app.models import Chunk, ChunkTopic, Material, MaterialPage, User
from app.schemas.academics import TopicCreate
from app.services.academics import topics
from tests.academics.conftest import forget_replans, make_rows
from tests.ai.conftest import (  # noqa: F401 (fixtures shared with the AI client tests)
    MakeClient,
    fake_llm,
    make_client,
    settings,
    sleeps,
    usage_sessions,
)
from tests.api.conftest import client_as  # noqa: F401 (HTTP clients acting as a user)

FIREWALL = (
    "A stateful inspection firewall tracks each TCP connection in a state table, so it "
    "can allow reply packets that belong to a connection it has already seen."
)
FILTER = "A packet filter firewall checks each packet against rules on addresses and ports."
PROXY = "An application proxy firewall relays traffic and inspects the application protocol."
CIPHER = "Symmetric ciphers such as AES use one shared key for encryption and decryption."
EXAM = "EXAM QUESTION 3: Explain how a stateful firewall differs from a packet filter."
PRIVATE = "MY OWN NOTES: firewalls, as I understood them in my essay."
OUTLINE = "COURSE OUTLINE: week 9 covers firewalls."


@dataclass
class Practice:
    """IDs only: the worker's rollbacks expire ORM objects."""

    user_id: uuid.UUID
    module_id: uuid.UUID
    chapter: uuid.UUID
    sub: uuid.UUID
    other: uuid.UUID
    # Chunk ids by their text constant's name.
    chunks: dict[str, uuid.UUID] = field(default_factory=dict)
    materials: dict[str, uuid.UUID] = field(default_factory=dict)


async def add_material(
    session: AsyncSession,
    user_id: uuid.UUID,
    module_id: uuid.UUID,
    title: str,
    kind: str,
    texts: list[str],
    *,
    allow_ai: bool = True,
) -> tuple[uuid.UUID, list[uuid.UUID]]:
    """A ready material with one chunk per page, straight into the database."""
    material = Material(
        id=uuid.uuid4(),
        user_id=user_id,
        module_id=module_id,
        kind=kind,
        title=title,
        original_filename=f"{title}.pdf",
        content_type="application/pdf",
        size_bytes=10,
        sha256=hashlib.sha256(title.encode()).hexdigest(),
        status="ready",
        page_count=len(texts),
        allow_ai=allow_ai,
    )
    session.add(material)
    await session.flush()
    chunk_ids = []
    for number, text in enumerate(texts, start=1):
        session.add(
            MaterialPage(
                user_id=user_id,
                material_id=material.id,
                page_number=number,
                text=text,
                char_count=len(text),
                is_scanned=False,
            )
        )
        await session.flush()
        chunk = Chunk(
            id=uuid.uuid4(),
            user_id=user_id,
            module_id=module_id,
            material_id=material.id,
            page_number=number,
            position=0,
            text=text,
            token_count=len(text.split()),
            embedding=[1.0] + [0.0] * 383,
        )
        session.add(chunk)
        chunk_ids.append(chunk.id)
    await session.flush()
    return material.id, chunk_ids


def link(
    module_id: uuid.UUID, chunk_id: uuid.UUID, topic_id: uuid.UUID, score: float
) -> ChunkTopic:
    return ChunkTopic(
        module_id=module_id, chunk_id=chunk_id, topic_id=topic_id, score=score, method="similarity"
    )


async def make_practice(session: AsyncSession, user: User, code: str = "COS330") -> Practice:
    rows = await make_rows(session, user, code)
    uid, module_id = user.id, rows.module.id
    chapter = rows.topic.id
    sub = (
        await topics.create_topic(
            session, module_id, TopicCreate(name="Firewall types", parent_id=chapter), user_id=uid
        )
    ).id
    other = (
        await topics.create_topic(session, module_id, TopicCreate(name="Ciphers"), user_id=uid)
    ).id
    found = Practice(uid, module_id, chapter, sub, other)

    slides, (firewall, filter_, proxy, cipher) = await add_material(
        session, uid, module_id, "CH09 Firewalls", "slides", [FIREWALL, FILTER, PROXY, CIPHER]
    )
    exam, (exam_chunk,) = await add_material(
        session, uid, module_id, "Exam 2025", "past_paper", [EXAM]
    )
    notes, (private,) = await add_material(
        session, uid, module_id, "My notes", "notes", [PRIVATE], allow_ai=False
    )
    outline, (outline_chunk,) = await add_material(
        session, uid, module_id, "Course outline", "outline", [OUTLINE]
    )
    found.materials = {"slides": slides, "exam": exam, "notes": notes, "outline": outline}
    found.chunks = {
        "FIREWALL": firewall,
        "FILTER": filter_,
        "PROXY": proxy,
        "CIPHER": cipher,
        "EXAM": exam_chunk,
        "PRIVATE": private,
        "OUTLINE": outline_chunk,
    }
    session.add_all(
        [
            link(module_id, firewall, chapter, 0.9),
            link(module_id, filter_, sub, 0.8),
            # Linked to both: its best score counts.
            link(module_id, proxy, chapter, 0.5),
            link(module_id, proxy, sub, 0.7),
            link(module_id, cipher, other, 0.9),
            # Higher scores than all the slides, and never sent.
            link(module_id, exam_chunk, chapter, 0.99),
            link(module_id, private, chapter, 0.98),
            link(module_id, outline_chunk, sub, 0.97),
        ]
    )
    await session.commit()
    await forget_replans(session, user)
    return found


@pytest.fixture
async def practice(session: AsyncSession, user_a: User) -> Practice:
    return await make_practice(session, user_a)


@pytest.fixture
def practice_llm(make_client: MakeClient) -> Iterator[LLMClient]:  # noqa: F811
    """The process's LLM client: the fake providers, usage logged into the test session."""
    client = make_client()
    set_llm_client(client)
    yield client
    set_llm_client(None)


def generated(*items: dict[str, Any]) -> str:
    return json.dumps({"items": list(items)})


def card(prompt: str, answer: str, sources: list[str], **extra: Any) -> dict[str, Any]:
    return {"kind": "flashcard", "prompt": prompt, "answer": answer, "sources": sources, **extra}


def question(prompt: str, answer: str, key_points: list[str], sources: list[str]) -> dict[str, Any]:
    return {
        "kind": "short_answer",
        "prompt": prompt,
        "answer": answer,
        "key_points": key_points,
        "sources": sources,
    }
