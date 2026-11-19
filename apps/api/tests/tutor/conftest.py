import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LLMClient, set_llm_client
from app.models import User
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
from tests.search.conftest import Page, add_material, run_jobs

FIREWALL = (
    "A stateful inspection firewall tracks each TCP connection in a state table, so it "
    "can allow reply packets that belong to a connection it has already seen."
)
FILTER = "A packet filter firewall checks each packet against rules on addresses and ports."
CIPHER = "Symmetric ciphers such as AES use one shared key for encryption and decryption."
PRIVATE = "MY OWN ANSWER: a stateful firewall tracks connections, as I wrote in my essay."


@dataclass(frozen=True)
class Module:
    """IDs only: the worker's rollbacks expire ORM objects."""

    user_id: uuid.UUID
    module_id: uuid.UUID
    topic_id: uuid.UUID
    study_id: uuid.UUID
    slides: uuid.UUID
    private: uuid.UUID


@pytest.fixture
async def module(session: AsyncSession, user_a: User, tmp_path: Path) -> Module:
    """Alice's indexed module: CH09 (two firewall pages and a cipher page) and her own
    answer with AI off. One topic, and one ended study session on it."""
    user_id = user_a.id
    rows = await make_rows(session, user_a)
    ids = (rows.module.id, rows.topic.id, rows.study_session.id)
    slides = await add_material(
        session,
        rows.user,
        rows.module,
        "CH09",
        [
            Page(FIREWALL, title="Stateful inspection"),
            Page(FILTER, title="Packet filters"),
            Page(CIPHER, title="Ciphers"),
        ],
    )
    private = await add_material(session, rows.user, rows.module, "u00000000 A1", [Page(PRIVATE)])
    private.allow_ai = False
    slides_id, private_id = slides.id, private.id
    await session.commit()
    await run_jobs(session, tmp_path)
    return Module(user_id, *ids, slides_id, private_id)


@pytest.fixture
def tutor_llm(make_client: MakeClient) -> Iterator[LLMClient]:  # noqa: F811
    """The process's LLM client: the fake providers, usage logged into the test session."""
    client = make_client()
    set_llm_client(client)
    yield client
    set_llm_client(None)


def sse_events(text: str) -> list[tuple[str, dict[str, Any]]]:
    """(event, data) for each server-sent event in a response body (keep-alives skipped)."""
    events: list[tuple[str, dict[str, Any]]] = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        name, data = "message", []
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].strip())
        if data:
            events.append((name, json.loads("\n".join(data))))
    return events
