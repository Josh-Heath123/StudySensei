"""Postgres itself rejects cross-user and cross-module links.

These inserts bypass the services on purpose: even buggy code that forgets a
user_id check can't create a row pointing at another user's (or module's) data.
"""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AssessmentTopic, Module, Task, Topic, User
from app.schemas.academics import ModuleCreate, ModuleUpdate
from app.services.academics import modules
from app.services.errors import Conflict
from tests.academics.conftest import Rows, make_rows


async def assert_rejected(session: AsyncSession, row: object) -> None:
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add(row)
            await session.flush()


async def test_topic_cannot_belong_to_another_users_module(
    session: AsyncSession, alice: Rows, user_b: User
) -> None:
    await assert_rejected(session, Topic(user_id=user_b.id, module_id=alice.module.id, name="X"))


async def test_topic_parent_must_be_in_same_module(session: AsyncSession, alice: Rows) -> None:
    other = await make_rows(session, alice.user, code="COS301")
    await assert_rejected(
        session,
        Topic(
            user_id=alice.user.id,
            module_id=other.module.id,
            parent_id=alice.topic.id,
            name="X",
        ),
    )


async def test_topic_cannot_be_its_own_parent(session: AsyncSession, alice: Rows) -> None:
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            alice.topic.parent_id = alice.topic.id
            await session.flush()


async def test_assessment_cannot_cover_topic_from_another_module(
    session: AsyncSession, alice: Rows
) -> None:
    other = await make_rows(session, alice.user, code="COS301")
    await assert_rejected(
        session,
        AssessmentTopic(
            assessment_id=alice.assessment.id,
            topic_id=other.topic.id,
            module_id=alice.module.id,
        ),
    )


async def test_assessment_cannot_cover_another_users_topic(
    session: AsyncSession, alice: Rows, bob: Rows
) -> None:
    await assert_rejected(
        session,
        AssessmentTopic(
            assessment_id=bob.assessment.id, topic_id=alice.topic.id, module_id=bob.module.id
        ),
    )


async def test_task_assessment_must_be_in_same_module(session: AsyncSession, alice: Rows) -> None:
    other = await make_rows(session, alice.user, code="COS301")
    await assert_rejected(
        session,
        Task(
            user_id=alice.user.id,
            module_id=other.module.id,
            assessment_id=alice.assessment.id,
            title="X",
        ),
    )


async def test_module_colour_must_be_hex(session: AsyncSession, user_a: User) -> None:
    await assert_rejected(session, Module(user_id=user_a.id, code="X1", name="X", colour="blue"))


async def test_module_code_unique_per_user_not_globally(
    session: AsyncSession, alice: Rows, user_b: User
) -> None:
    # Bob can use Alice's code...
    await modules.create_module(
        session, ModuleCreate(code="COS330", name="Bob's copy"), user_id=user_b.id
    )
    # ...but Alice can't reuse her own, through the service or directly.
    with pytest.raises(Conflict):
        await modules.create_module(
            session, ModuleCreate(code="COS330", name="Duplicate"), user_id=alice.user.id
        )
    await assert_rejected(
        session, Module(user_id=alice.user.id, code="COS330", name="Dup", colour="#000000")
    )


async def test_renaming_to_an_existing_code_conflicts_and_session_survives(
    session: AsyncSession, alice: Rows
) -> None:
    other = await modules.create_module(
        session, ModuleCreate(code="cos301", name="Other"), user_id=alice.user.id
    )

    with pytest.raises(Conflict, match="COS330"):
        await modules.update_module(
            session, other.id, ModuleUpdate(code="cos330"), user_id=alice.user.id
        )

    # Only the failed change was rolled back; earlier rows are still loaded and usable.
    fresh = await modules.get_module(session, other.id, user_id=alice.user.id)
    assert fresh.code == "COS301"
    assert alice.module.code == "COS330"
