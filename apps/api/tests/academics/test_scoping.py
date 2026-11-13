"""One user can never read or change another user's academic rows.

Bob holds the IDs of every row Alice owns and tries every service operation
with them. Each attempt must behave exactly like a missing ID (NotFound),
and Alice's data must be untouched afterwards.
"""

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Assessment, AssessmentTopic, Task, Topic
from app.schemas.academics import (
    AssessmentCreate,
    AssessmentUpdate,
    ModuleUpdate,
    TaskCreate,
    TaskUpdate,
    TopicCreate,
    TopicUpdate,
)
from app.services.academics import assessments, modules, tasks, topics
from app.services.errors import NotFound
from tests.academics.conftest import Rows

KINDS = ["module", "topic", "assessment", "task"]

Getter = Callable[..., Awaitable[Any]]

GETTERS: dict[str, Getter] = {
    "module": modules.get_module,
    "topic": topics.get_topic,
    "assessment": assessments.get_assessment,
    "task": tasks.get_task,
}

DELETERS: dict[str, Getter] = {
    "module": modules.delete_module,
    "topic": topics.delete_topic,
    "assessment": assessments.delete_assessment,
    "task": tasks.delete_task,
}

# (update function, payload, attribute that payload would change)
UPDATERS: dict[str, tuple[Getter, Any, str]] = {
    "module": (modules.update_module, ModuleUpdate(name="Hacked"), "name"),
    "topic": (topics.update_topic, TopicUpdate(name="Hacked"), "name"),
    "assessment": (assessments.update_assessment, AssessmentUpdate(title="Hacked"), "title"),
    "task": (tasks.update_task, TaskUpdate(title="Hacked"), "title"),
}


def row_of(rows: Rows, kind: str) -> Any:
    return getattr(rows, kind)


@pytest.mark.parametrize("kind", KINDS)
async def test_cannot_read_another_users_row(
    session: AsyncSession, alice: Rows, bob: Rows, kind: str
) -> None:
    with pytest.raises(NotFound):
        await GETTERS[kind](session, row_of(alice, kind).id, user_id=bob.user.id)


@pytest.mark.parametrize("kind", KINDS)
async def test_cannot_update_another_users_row(
    session: AsyncSession, alice: Rows, bob: Rows, kind: str
) -> None:
    update, payload, attr = UPDATERS[kind]
    original = getattr(row_of(alice, kind), attr)

    with pytest.raises(NotFound):
        await update(session, row_of(alice, kind).id, payload, user_id=bob.user.id)

    fresh = await GETTERS[kind](session, row_of(alice, kind).id, user_id=alice.user.id)
    assert getattr(fresh, attr) == original


@pytest.mark.parametrize("kind", KINDS)
async def test_cannot_delete_another_users_row(
    session: AsyncSession, alice: Rows, bob: Rows, kind: str
) -> None:
    with pytest.raises(NotFound):
        await DELETERS[kind](session, row_of(alice, kind).id, user_id=bob.user.id)

    # Still there for Alice.
    await GETTERS[kind](session, row_of(alice, kind).id, user_id=alice.user.id)


async def test_lists_only_return_own_rows(session: AsyncSession, alice: Rows, bob: Rows) -> None:
    def ids(rows: list[Any]) -> set[uuid.UUID]:
        return {r.id for r in rows}

    for me, other in [(alice, bob), (bob, alice)]:
        uid = me.user.id
        assert ids(await modules.list_modules(session, user_id=uid)) == {me.module.id}
        assert ids(await topics.list_topics(session, me.module.id, user_id=uid)) == {me.topic.id}
        assert ids(await assessments.list_assessments(session, user_id=uid)) == {me.assessment.id}
        assert ids(await tasks.list_tasks(session, user_id=uid)) == {me.task.id}

        # Listing the other user's module is NotFound, as for a missing one.
        other_module = other.module.id
        with pytest.raises(NotFound):
            await assessments.list_assessments(session, user_id=uid, module_id=other_module)
        with pytest.raises(NotFound):
            await tasks.list_tasks(session, user_id=uid, module_id=other_module)
        with pytest.raises(NotFound):
            await topics.list_topics(session, other_module, user_id=uid)
        with pytest.raises(NotFound):
            await assessments.get_assessment_topic_ids(session, other.assessment.id, user_id=uid)


# --- Bob can't attach his own rows to Alice's ------------------------------------------


async def _counts(session: AsyncSession, user_id: uuid.UUID) -> tuple[int, ...]:
    async def count(model: Any) -> int:
        return (
            await session.scalar(
                select(func.count()).select_from(model).where(model.user_id == user_id)
            )
            or 0
        )

    links = await session.scalar(
        select(func.count())
        .select_from(AssessmentTopic)
        .join(Assessment, Assessment.id == AssessmentTopic.assessment_id)
        .where(Assessment.user_id == user_id)
    )
    return (await count(Topic), await count(Assessment), await count(Task), links or 0)


CROSS_USER_WRITES: dict[str, Callable[[AsyncSession, Rows, Rows], Awaitable[Any]]] = {
    "topic in her module": lambda s, a, b: topics.create_topic(
        s, a.module.id, TopicCreate(name="Mine now"), user_id=b.user.id
    ),
    "assessment in her module": lambda s, a, b: assessments.create_assessment(
        s, a.module.id, AssessmentCreate(title="Mine now", kind="exam"), user_id=b.user.id
    ),
    "task in her module": lambda s, a, b: tasks.create_task(
        s, a.module.id, TaskCreate(title="Mine now"), user_id=b.user.id
    ),
    "topic under her topic": lambda s, a, b: topics.create_topic(
        s, b.module.id, TopicCreate(name="Child", parent_id=a.topic.id), user_id=b.user.id
    ),
    "move his topic under hers": lambda s, a, b: topics.move_topic(
        s, b.topic.id, new_parent_id=a.topic.id, position=0, user_id=b.user.id
    ),
    "link her topic to his assessment": lambda s, a, b: assessments.set_assessment_topics(
        s, b.assessment.id, {a.topic.id}, user_id=b.user.id
    ),
    "new task on her assessment": lambda s, a, b: tasks.create_task(
        s, b.module.id, TaskCreate(title="Sneaky", assessment_id=a.assessment.id), user_id=b.user.id
    ),
    "move his task onto her assessment": lambda s, a, b: tasks.update_task(
        s, b.task.id, TaskUpdate(assessment_id=a.assessment.id), user_id=b.user.id
    ),
}


@pytest.mark.parametrize("attempt", CROSS_USER_WRITES)
async def test_cannot_attach_to_another_users_rows(
    session: AsyncSession, alice: Rows, bob: Rows, attempt: str
) -> None:
    before = (await _counts(session, alice.user.id), await _counts(session, bob.user.id))

    with pytest.raises(NotFound):
        await CROSS_USER_WRITES[attempt](session, alice, bob)

    after = (await _counts(session, alice.user.id), await _counts(session, bob.user.id))
    assert after == before
    # Bob's own rows still point where they did.
    assert (await topics.get_topic(session, bob.topic.id, user_id=bob.user.id)).parent_id is None
    task = await tasks.get_task(session, bob.task.id, user_id=bob.user.id)
    assert task.assessment_id == bob.assessment.id
