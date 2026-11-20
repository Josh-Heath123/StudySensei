"""Moving a stored block (decision 0022): the move re-plans with the block pinned, pinned blocks
are carried past the 24 h window while valid and dropped when not, and refused moves say why."""

from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AvailabilityException, PlanBlock, PlanVersion, User
from app.services.errors import Conflict, Invalid
from app.services.planning.replan import move_block, replan
from tests.planning.test_replan import NOW, blocks_of, setup
from tests.planning.test_replan_fixes import start_on


def minutes(blocks: list[PlanBlock]) -> int:
    return sum(int((b.end_at - b.start_at).total_seconds() // 60) for b in blocks if b.topic_id)


async def later_block(session: AsyncSession, version: PlanVersion) -> PlanBlock:
    """A study block more than 24 h away (so it isn't fixed anyway)."""
    return next(
        b
        for b in await blocks_of(session, version)
        if b.topic_id and b.start_at > NOW + timedelta(hours=30)
    )


async def test_a_move_pins_the_block_at_its_new_time(session: AsyncSession, user_a: User) -> None:
    await setup(session, user_a)
    first = await replan(session, user_id=user_a.id, now=NOW, trigger="initial")
    block = await later_block(session, first)
    # Thursday 4 March, 20:10: free (evenings 18:00-21:00) and clear of other blocks.
    target = (NOW + timedelta(days=3)).replace(hour=20, minute=10)
    taken = {b.start_at for b in await blocks_of(session, first)}
    assert all(
        abs((t - target).total_seconds()) >= 60 * 60 for t in taken if t.date() == target.date()
    )

    second = await move_block(session, block.id, target, user_id=user_a.id, now=NOW)

    assert (second.number, second.trigger) == (2, "move")
    local = block.start_at.astimezone(target.tzinfo)
    assert second.summary == (
        f"You moved Microservices from {local:%a} {local.day} Mar, {local:%H:%M} "
        "to Thu 4 Mar, 20:10."
    )
    copy = next(b for b in await blocks_of(session, second) if b.start_at == target)
    assert (copy.pinned, copy.fixed, copy.reason_text) == (True, True, block.reason_text)
    await session.refresh(block)
    assert (block.version_id, block.start_at, block.status) == (first.id, block.start_at, "planned")
    assert minutes(await blocks_of(session, second)) == minutes(await blocks_of(session, first))


async def test_a_pinned_block_is_carried_while_valid_and_dropped_when_not(
    session: AsyncSession, user_a: User
) -> None:
    await setup(session, user_a)
    first = await replan(session, user_id=user_a.id, now=NOW, trigger="initial")
    block = await later_block(session, first)
    target = (NOW + timedelta(days=3)).replace(hour=20, minute=10)
    await move_block(session, block.id, target, user_id=user_a.id, now=NOW)

    # Another change, far from it: the pinned block is carried at its time.
    session.add(
        AvailabilityException(
            user_id=user_a.id, date=(NOW + timedelta(days=5)).date(), unavailable=True, windows=[]
        )
    )
    await session.commit()
    third = await replan(session, user_id=user_a.id, now=NOW, trigger="availability")
    carried = [b for b in await blocks_of(session, third) if b.start_at == target]
    assert len(carried) == 1 and carried[0].pinned

    # Its day becomes unavailable: it's dropped, and the unit's time is placed again.
    session.add(
        AvailabilityException(user_id=user_a.id, date=target.date(), unavailable=True, windows=[])
    )
    await session.commit()
    fourth = await replan(session, user_id=user_a.id, now=NOW, trigger="availability")
    after = await blocks_of(session, fourth)
    assert all(b.start_at.date() != target.date() for b in after)
    assert not any(b.pinned for b in after)
    assert minutes(after) == minutes(await blocks_of(session, third))


@pytest.mark.parametrize(
    ("hour", "minute", "text"),
    [
        (10, 0, "That's outside your study time on Thu 4 Mar."),
        (20, 15, "That's outside your study time on Thu 4 Mar."),  # ends 21:05
    ],
)
async def test_a_refused_move_says_why(
    session: AsyncSession, user_a: User, hour: int, minute: int, text: str
) -> None:
    await setup(session, user_a)
    first = await replan(session, user_id=user_a.id, now=NOW, trigger="initial")
    block = await later_block(session, first)
    target = (NOW + timedelta(days=3)).replace(hour=hour, minute=minute)

    with pytest.raises(Invalid, match=text):
        await move_block(session, block.id, target, user_id=user_a.id, now=NOW)


async def test_only_an_unstarted_block_without_a_session_moves(
    session: AsyncSession, user_a: User
) -> None:
    rows = await setup(session, user_a)
    first = await replan(session, user_id=user_a.id, now=NOW, trigger="initial")
    tonight = (await blocks_of(session, first))[0]
    target = (NOW + timedelta(days=3)).replace(hour=20, minute=10)

    with pytest.raises(Conflict, match="It has already started"):
        await move_block(
            session,
            tonight.id,
            target,
            user_id=user_a.id,
            now=tonight.start_at + timedelta(minutes=1),
        )
    await start_on(session, rows, tonight)
    with pytest.raises(Conflict, match="It has a session"):
        await move_block(session, tonight.id, target, user_id=user_a.id, now=NOW)
