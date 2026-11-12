import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Topic
from app.schemas.academics import TopicCreate, TopicUpdate
from app.services.academics import topics
from app.services.errors import Invalid
from tests.academics.conftest import Rows, make_rows


async def add(
    session: AsyncSession, rows: Rows, name: str, parent: Topic | None = None, position: int = 0
) -> Topic:
    return await topics.create_topic(
        session,
        rows.module.id,
        TopicCreate(name=name, parent_id=parent.id if parent else None, position=position),
        user_id=rows.user.id,
    )


def shape(nodes: list[topics.TopicNode]) -> list[object]:
    return [(n.topic.name, shape(n.children)) if n.children else n.topic.name for n in nodes]


async def test_builds_nested_tree_in_position_order(session: AsyncSession, alice: Rows) -> None:
    # alice.topic ("Microservices") is already a root at position 0.
    patterns = await add(session, alice, "Patterns", position=1)
    await add(session, alice, "Observer", patterns, position=1)
    creational = await add(session, alice, "Creational", patterns, position=0)
    await add(session, alice, "Factory", creational)

    tree = topics.build_tree(
        await topics.list_topics(session, alice.module.id, user_id=alice.user.id)
    )

    assert shape(tree) == [
        "Microservices",
        ("Patterns", [("Creational", ["Factory"]), "Observer"]),
    ]


async def test_deleting_a_topic_deletes_its_subtree(session: AsyncSession, alice: Rows) -> None:
    child = await add(session, alice, "Child", alice.topic)
    await add(session, alice, "Grandchild", child)
    keep = await add(session, alice, "Sibling")

    await topics.delete_topic(session, alice.topic.id, user_id=alice.user.id)

    remaining = await topics.list_topics(session, alice.module.id, user_id=alice.user.id)
    assert [t.id for t in remaining] == [keep.id]


async def test_move_to_root_and_under_another_topic(session: AsyncSession, alice: Rows) -> None:
    child = await add(session, alice, "Child", alice.topic)
    other = await add(session, alice, "Other", position=1)

    # A position past the end is clamped: it becomes the only (index 0) child.
    moved = await topics.move_topic(
        session, child.id, new_parent_id=other.id, position=3, user_id=alice.user.id
    )
    assert (moved.parent_id, moved.position) == (other.id, 0)

    moved = await topics.move_topic(
        session, child.id, new_parent_id=None, position=0, user_id=alice.user.id
    )
    assert moved.parent_id is None


async def test_cannot_move_under_itself_or_a_descendant(session: AsyncSession, alice: Rows) -> None:
    child = await add(session, alice, "Child", alice.topic)
    grandchild = await add(session, alice, "Grandchild", child)

    for target in (alice.topic, child, grandchild):
        with pytest.raises(Invalid):
            await topics.move_topic(
                session, alice.topic.id, new_parent_id=target.id, position=0, user_id=alice.user.id
            )


async def test_parent_must_be_in_the_same_module(session: AsyncSession, alice: Rows) -> None:
    other = await make_rows(session, alice.user, code="COS301")

    with pytest.raises(Invalid):
        await add(session, other, "Child", parent=alice.topic)
    with pytest.raises(Invalid):
        await topics.move_topic(
            session, other.topic.id, new_parent_id=alice.topic.id, position=0, user_id=alice.user.id
        )


async def test_user_edit_claims_an_ai_topic(session: AsyncSession, alice: Rows) -> None:
    alice.topic.source = "ai"
    await session.flush()

    updated = await topics.update_topic(
        session, alice.topic.id, TopicUpdate(name="Renamed"), user_id=alice.user.id
    )

    assert (updated.name, updated.source) == ("Renamed", "user")


async def positions(session: AsyncSession, rows: Rows) -> dict[str, int]:
    return {
        t.name: t.position
        for t in await topics.list_topics(session, rows.module.id, user_id=rows.user.id)
    }


async def test_new_topics_append_after_their_siblings(session: AsyncSession, alice: Rows) -> None:
    second = await topics.create_topic(
        session, alice.module.id, TopicCreate(name="Second"), user_id=alice.user.id
    )
    first_child = await add(session, alice, "First child", alice.topic)

    assert second.position == 1  # after "Microservices"
    assert first_child.position == 0  # first under its own parent


async def test_moves_renumber_old_and_new_siblings(session: AsyncSession, alice: Rows) -> None:
    uid = alice.user.id
    b = await topics.create_topic(session, alice.module.id, TopicCreate(name="B"), user_id=uid)
    c = await topics.create_topic(session, alice.module.id, TopicCreate(name="C"), user_id=uid)
    # Roots: Microservices 0, B 1, C 2

    await topics.move_topic(session, c.id, new_parent_id=None, position=0, user_id=uid)
    assert await positions(session, alice) == {"C": 0, "Microservices": 1, "B": 2}

    # Indent B under C: roots close the gap, B becomes C's first child.
    await topics.move_topic(session, b.id, new_parent_id=c.id, position=0, user_id=uid)
    assert await positions(session, alice) == {"C": 0, "Microservices": 1, "B": 0}


async def test_delete_closes_the_gap(session: AsyncSession, alice: Rows) -> None:
    uid = alice.user.id
    b = await topics.create_topic(session, alice.module.id, TopicCreate(name="B"), user_id=uid)
    await topics.create_topic(session, alice.module.id, TopicCreate(name="C"), user_id=uid)

    await topics.delete_topic(session, b.id, user_id=uid)

    assert await positions(session, alice) == {"Microservices": 0, "C": 1}
