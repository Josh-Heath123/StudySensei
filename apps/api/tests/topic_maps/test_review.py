"""Reviewing AI topics (decision 0009): keep, rename, merge into, dismiss, restore, keep
all, the review stats, linked pages and unlinking."""

import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChunkTopic, Topic, TopicPage, TopicReview, User
from app.schemas.topic_maps import ModuleTopicMap
from app.services.topic_maps.merge import apply_merge
from app.services.topic_maps.prompts import MergeRefs
from tests.api.conftest import ClientFactory
from tests.topic_maps.conftest import AUTH, SESSIONS, Module
from tests.topic_maps.test_linking import a_topic, cite, link, links


@pytest.fixture
async def api(
    client_as: ClientFactory, session: AsyncSession, module: Module
) -> AsyncIterator[AsyncClient]:
    user = await session.get(User, module.user_id)
    assert user is not None
    async with client_as(user) as client:
        yield client


async def topic(session: AsyncSession, topic_id: uuid.UUID) -> Topic | None:
    return await session.scalar(
        select(Topic).where(Topic.id == topic_id).execution_options(populate_existing=True)
    )


async def child_of(
    session: AsyncSession, module: Module, parent: uuid.UUID, name: str, source: str = "ai"
) -> uuid.UUID:
    child = Topic(
        user_id=module.user_id,
        module_id=module.module_id,
        parent_id=parent,
        name=name,
        source=source,
        position=0,
    )
    session.add(child)
    await session.commit()
    return child.id


async def review(api: AsyncClient, module: Module) -> dict[str, int]:
    response = await api.get(f"/modules/{module.module_id}/topic-map")
    assert response.status_code == 200
    stats: dict[str, int] = response.json()["review"]
    return stats


async def cited_pages(session: AsyncSession, topic_id: uuid.UUID) -> list[int]:
    rows = await session.scalars(
        select(TopicPage.page_number)
        .where(TopicPage.topic_id == topic_id)
        .order_by(TopicPage.page_number)
    )
    return list(rows)


def merge_tree(*names: str, sub: str | None = None) -> ModuleTopicMap:
    """Top-level topics citing "M1.1"; ``sub`` goes under the first one."""
    return ModuleTopicMap.model_validate(
        {
            "topics": [
                {"name": name, "sources": ["M1.1"], "subtopics": [sub] if sub and i == 0 else []}
                for i, name in enumerate(names)
            ]
        }
    )


async def merge(session: AsyncSession, module: Module, tree: ModuleTopicMap) -> int:
    """Apply a merged tree whose every node cites page 3 of the slides; returns topics added."""
    refs = MergeRefs(existing={}, proposals={"M1.1": (module.slides, (3,))})
    outcome = await apply_merge(session, module.module_id, tree, refs, user_id=module.user_id)
    await session.commit()
    return outcome.created


# --- keep, rename, keep all, stats ---


async def test_keep_makes_an_ai_topic_the_students_and_counts_it(
    api: AsyncClient, session: AsyncSession, module: Module
) -> None:
    firewalls = await a_topic(session, module, "Firewalls")
    await a_topic(session, module, "Intrusion detection")
    assert await review(api, module) == {
        "kept": 0,
        "renamed": 0,
        "merged": 0,
        "dismissed": 0,
        "unreviewed": 2,
    }

    response = await api.post(f"/topics/{firewalls}/keep")

    assert response.status_code == 200 and response.json()["source"] == "user"
    stats = await review(api, module)
    assert (stats["kept"], stats["unreviewed"]) == (1, 1)
    # Keeping again (or keeping the student's own topic) changes nothing.
    assert (await api.post(f"/topics/{firewalls}/keep")).status_code == 200
    assert (await api.post(f"/topics/{module.topic_id}/keep")).status_code == 200
    assert (await review(api, module))["kept"] == 1


async def test_renaming_counts_as_renamed_even_after_keeping(
    api: AsyncClient, session: AsyncSession, module: Module
) -> None:
    first = await a_topic(session, module, "Firewall")
    second = await a_topic(session, module, "IDS")
    await api.post(f"/topics/{second}/keep")

    await api.patch(f"/topics/{first}", json={"name": "Firewalls"})
    await api.patch(f"/topics/{second}", json={"name": "Intrusion detection"})
    # A description or a move alone keeps it ("kept with a small edit").
    third = await a_topic(session, module, "Honeypots")
    await api.patch(f"/topics/{third}", json={"description": "Decoys."})

    stats = await review(api, module)
    assert (stats["renamed"], stats["kept"], stats["unreviewed"]) == (2, 1, 0)
    row = await session.scalar(select(TopicReview).where(TopicReview.topic_id == first))
    assert row is not None and (row.name, row.target_id) == ("Firewall", first)


async def test_the_students_own_topics_are_never_counted(
    api: AsyncClient, session: AsyncSession, module: Module
) -> None:
    await api.patch(f"/topics/{module.topic_id}", json={"name": "Service architecture"})

    assert await review(api, module) == dict.fromkeys(
        ("kept", "renamed", "merged", "dismissed", "unreviewed"), 0
    )


async def test_keep_all_confirms_every_remaining_ai_topic(
    api: AsyncClient, session: AsyncSession, module: Module
) -> None:
    parent = await a_topic(session, module, "Network security")
    await child_of(session, module, parent, "Firewalls")
    await api.patch(f"/topics/{parent}", json={"name": "Networks"})

    response = await api.post(f"/modules/{module.module_id}/topics/keep-all")

    assert response.json() == {"kept": 1}
    stats = await review(api, module)
    assert (stats["kept"], stats["renamed"], stats["unreviewed"]) == (1, 1, 0)
    sources = await session.scalars(select(Topic.source).where(Topic.module_id == module.module_id))
    assert set(sources) == {"user"}


# --- merge into ---


async def test_merge_into_moves_children_pages_and_links_then_deletes(
    api: AsyncClient, session: AsyncSession, module: Module
) -> None:
    target = await a_topic(session, module, "Authentication")
    await child_of(session, module, target, "Passwords", source="user")
    merged = await a_topic(session, module, "Session management")
    child = await child_of(session, module, merged, "Session tokens")
    await cite(session, module, merged, 3)
    await cite(session, module, target, 1)
    await link(session, module, threshold=0.99)
    assert [text for text, _, _ in await links(session, merged)] == [SESSIONS]

    response = await api.post(f"/topics/{merged}/merge-into", json={"target_id": str(target)})

    assert response.status_code == 200
    assert response.json()["id"] == str(target) and response.json()["source"] == "user"
    assert await topic(session, merged) is None
    moved = await topic(session, child)
    assert moved is not None and (moved.parent_id, moved.position) == (target, 1)
    assert await cited_pages(session, target) == [1, 3]
    assert sorted(text for text, _, _ in await links(session, target)) == sorted([AUTH, SESSIONS])
    stats = await review(api, module)
    # The merged topic, and the target (chosen as its home) is confirmed.
    assert (stats["merged"], stats["kept"], stats["unreviewed"]) == (1, 1, 1)


async def test_merge_into_refuses_itself_and_its_own_subtopics(
    api: AsyncClient, session: AsyncSession, module: Module
) -> None:
    parent = await a_topic(session, module, "Security")
    child = await child_of(session, module, parent, "Firewalls")

    itself = await api.post(f"/topics/{parent}/merge-into", json={"target_id": str(parent)})
    below = await api.post(f"/topics/{parent}/merge-into", json={"target_id": str(child)})
    missing = await api.post(f"/topics/{parent}/merge-into", json={"target_id": str(uuid.uuid4())})

    assert (itself.status_code, below.status_code, missing.status_code) == (422, 422, 404)
    assert "own subtopics" in below.json()["detail"]
    assert await topic(session, parent) is not None


async def test_a_merged_name_proposed_again_adds_to_the_target(
    api: AsyncClient, session: AsyncSession, module: Module
) -> None:
    target = await a_topic(session, module, "Authentication")
    merged = await a_topic(session, module, "Logging in")
    await api.post(f"/topics/{merged}/merge-into", json={"target_id": str(target)})
    renamed = await a_topic(session, module, "Firewall")
    await api.patch(f"/topics/{renamed}", json={"name": "Packet filters"})

    created = await merge(session, module, merge_tree("Logging in", "firewall"))

    assert created == 0
    assert await cited_pages(session, target) == [3]
    assert await cited_pages(session, renamed) == [3]


# --- dismiss and restore ---


async def test_dismiss_deletes_the_ai_subtree_but_keeps_the_students_topics(
    api: AsyncClient, session: AsyncSession, module: Module
) -> None:
    root = await a_topic(session, module, "Chapter 9")
    dismissed = await child_of(session, module, root, "Firewalls")
    ai_child = await child_of(session, module, dismissed, "Packet filters")
    own_child = await child_of(session, module, dismissed, "My notes", source="user")

    response = await api.post(f"/topics/{dismissed}/dismiss")

    assert response.json() == {"dismissed": 2}
    assert await topic(session, dismissed) is None and await topic(session, ai_child) is None
    kept = await topic(session, own_child)
    assert kept is not None and kept.parent_id == root
    listed = (await api.get(f"/modules/{module.module_id}/dismissed-topics")).json()
    assert sorted(item["name"] for item in listed) == ["Firewalls", "Packet filters"]
    assert (await review(api, module))["dismissed"] == 2


async def test_only_unreviewed_ai_topics_can_be_dismissed(
    api: AsyncClient, session: AsyncSession, module: Module
) -> None:
    response = await api.post(f"/topics/{module.topic_id}/dismiss")

    assert response.status_code == 422
    assert await topic(session, module.topic_id) is not None


async def test_a_dismissed_name_never_comes_back_in_a_merge(
    api: AsyncClient, session: AsyncSession, module: Module
) -> None:
    dismissed = await a_topic(session, module, "Firewalls")
    await api.post(f"/topics/{dismissed}/dismiss")

    # Same name, different case and punctuation; and a subtopic the AI put under it.
    created = await merge(session, module, merge_tree("FIREWALLS!", "Encryption", sub="Proxies"))

    names = set(
        await session.scalars(select(Topic.name).where(Topic.module_id == module.module_id))
    )
    assert created == 1
    assert "Encryption" in names
    assert not names & {"FIREWALLS!", "Firewalls", "Proxies"}


async def test_restore_brings_a_dismissed_topic_back_as_kept(
    api: AsyncClient, session: AsyncSession, module: Module
) -> None:
    parent = await a_topic(session, module, "Chapter 9")
    dismissed = await child_of(session, module, parent, "Firewalls")
    row = await session.get(Topic, dismissed)
    assert row is not None
    row.description = "Filtering traffic."
    await session.commit()
    await cite(session, module, dismissed, 3)
    await api.post(f"/topics/{dismissed}/dismiss")
    listed = (await api.get(f"/modules/{module.module_id}/dismissed-topics")).json()

    response = await api.post(f"/dismissed-topics/{listed[0]['id']}/restore")

    assert response.status_code == 200
    restored = response.json()
    assert (restored["name"], restored["description"], restored["parent_id"]) == (
        "Firewalls",
        "Filtering traffic.",
        str(parent),
    )
    assert restored["source"] == "user"
    assert await cited_pages(session, uuid.UUID(restored["id"])) == [3]
    assert (await api.get(f"/modules/{module.module_id}/dismissed-topics")).json() == []
    stats = await review(api, module)
    assert (stats["dismissed"], stats["kept"]) == (0, 1)
    # Restored twice? It's no longer dismissed.
    again = await api.post(f"/dismissed-topics/{listed[0]['id']}/restore")
    assert again.status_code == 404
    # And a merge proposing it adds to the restored topic instead of a duplicate.
    assert await merge(session, module, merge_tree("Firewalls")) == 0


async def test_restore_goes_to_the_top_level_when_the_parent_is_gone(
    api: AsyncClient, session: AsyncSession, module: Module
) -> None:
    parent = await a_topic(session, module, "Chapter 9")
    dismissed = await child_of(session, module, parent, "Firewalls")
    await api.post(f"/topics/{dismissed}/dismiss")
    await api.delete(f"/topics/{parent}")
    listed = (await api.get(f"/modules/{module.module_id}/dismissed-topics")).json()

    restored = (await api.post(f"/dismissed-topics/{listed[0]['id']}/restore")).json()

    assert restored["parent_id"] is None


# --- linked pages and unlinking ---


async def test_linked_pages_are_grouped_by_material_with_how_they_were_linked(
    api: AsyncClient, session: AsyncSession, module: Module
) -> None:
    security = await a_topic(session, module, "Session tokens", SESSIONS)
    await cite(session, module, security, 1)
    await link(session, module, threshold=0.5)

    response = await api.get(f"/topics/{security}/pages")

    assert response.status_code == 200
    [slides] = response.json()
    assert (slides["material_id"], slides["title"]) == (str(module.slides), "Week 1 Security")
    by_page = {page["page_number"]: page for page in slides["pages"]}
    assert by_page[1] == {"page_number": 1, "label": "Passwords", "method": "pages", "score": None}
    assert by_page[3]["method"] == "similarity" and 0.5 <= by_page[3]["score"] <= 1
    assert by_page[3]["label"] == "Sessions"
    assert [page["page_number"] for page in slides["pages"]] == sorted(by_page)


async def test_an_unlinked_page_stays_unlinked_after_relinking(
    api: AsyncClient, session: AsyncSession, module: Module
) -> None:
    security = await a_topic(session, module, "Session tokens", SESSIONS)
    await cite(session, module, security, 1)
    await link(session, module, threshold=0.5)
    assert sorted(text for text, _, _ in await links(session, security)) == sorted([AUTH, SESSIONS])

    for page in (1, 3):
        response = await api.delete(f"/topics/{security}/pages/{module.slides}/{page}")
        assert response.status_code == 204
    assert await links(session, security) == []

    await link(session, module, threshold=0.5)  # cited page 1, similar page 3: both stay out

    assert await links(session, security) == []
    assert (await api.get(f"/topics/{security}/pages")).json() == []
    tree = (await api.get(f"/modules/{module.module_id}/topics")).json()
    assert next(n for n in tree if n["id"] == str(security))["linked_pages"] == 0


async def test_unlinking_a_page_of_another_modules_material_is_404(
    api: AsyncClient, session: AsyncSession, module: Module
) -> None:
    security = await a_topic(session, module, "Security")

    response = await api.delete(f"/topics/{security}/pages/{uuid.uuid4()}/1")

    assert response.status_code == 404
    assert list(await session.scalars(select(ChunkTopic.id))) == []
