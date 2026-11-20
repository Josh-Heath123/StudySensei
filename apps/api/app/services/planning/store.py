"""Planning data in the database: settings, rules, exceptions, and a topic's workload and
confidence. Every query is scoped by ``user_id``; the pure logic is in ``availability.py``
and ``workload.py``."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, literal, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.queue import enqueue_replan
from app.models import (
    AvailabilityException,
    AvailabilityRule,
    Chunk,
    ChunkTopic,
    Material,
    Topic,
    User,
)
from app.schemas.planning import (
    MAX_RANGE_DAYS,
    ExceptionCreate,
    ExceptionUpdate,
    PlanningSettingsUpdate,
    RuleCreate,
    RuleUpdate,
    TopicPlanningUpdate,
    WindowIn,
)
from app.services.academics.modules import get_module
from app.services.academics.topics import get_topic
from app.services.errors import Conflict, Invalid, NotFound
from app.services.planning.availability import (
    Day,
    DayException,
    Rule,
    Window,
    check_windows,
    expand,
    format_minute,
    parse_minute,
    weekly_minutes,
)
from app.services.planning.subtree import Page, SubtreeWorkload, Tree, make_tree, subtree_workload
from app.services.planning.workload import SLIDE_KINDS, TEXT_KINDS, Workload, workload

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


async def _user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFound("User")
    return user


# --- settings --------------------------------------------------------------------------


async def get_settings(session: AsyncSession, *, user_id: uuid.UUID) -> User:
    return await _user(session, user_id)


async def update_settings(
    session: AsyncSession, data: PlanningSettingsUpdate, *, user_id: uuid.UUID
) -> User:
    user = await _user(session, user_id)
    changes = data.model_dump(exclude_unset=True)
    for name, value in changes.items():
        setattr(user, name, value)
    # The reminder lead doesn't change the plan.
    if changes.keys() - {"reminder_minutes"}:
        await enqueue_replan(session, user_id=user_id, trigger="availability")
    await session.commit()
    return user


# --- rules -----------------------------------------------------------------------------


@asynccontextmanager
async def _no_overlap(session: AsyncSession, weekday: int) -> AsyncIterator[None]:
    """Postgres decides overlaps (the exclusion constraint); say which day."""
    try:
        async with session.begin_nested():
            yield
            await session.flush()
    except IntegrityError as exc:
        if "ex_availability_rules_overlap" not in str(exc.orig):
            raise
        raise Conflict(f"That window overlaps another on {WEEKDAYS[weekday]}.") from exc


async def list_rules(session: AsyncSession, *, user_id: uuid.UUID) -> list[AvailabilityRule]:
    result = await session.scalars(
        select(AvailabilityRule)
        .where(AvailabilityRule.user_id == user_id)
        .order_by(AvailabilityRule.weekday, AvailabilityRule.start_minute)
    )
    return list(result)


async def get_rule(
    session: AsyncSession, rule_id: uuid.UUID, *, user_id: uuid.UUID
) -> AvailabilityRule:
    rule = await session.scalar(
        select(AvailabilityRule).where(
            AvailabilityRule.id == rule_id, AvailabilityRule.user_id == user_id
        )
    )
    if rule is None:
        raise NotFound("Availability rule")
    return rule


async def create_rule(
    session: AsyncSession, data: RuleCreate, *, user_id: uuid.UUID
) -> AvailabilityRule:
    window = data.minutes()
    rule = AvailabilityRule(
        user_id=user_id, weekday=data.weekday, start_minute=window.start, end_minute=window.end
    )
    async with _no_overlap(session, data.weekday):
        session.add(rule)
    await enqueue_replan(session, user_id=user_id, trigger="availability")
    await session.commit()
    return rule


async def update_rule(
    session: AsyncSession, rule_id: uuid.UUID, data: RuleUpdate, *, user_id: uuid.UUID
) -> AvailabilityRule:
    rule = await get_rule(session, rule_id, user_id=user_id)
    changes = data.model_dump(exclude_unset=True)
    weekday = changes.get("weekday", rule.weekday)
    start = parse_minute(changes["start"]) if "start" in changes else rule.start_minute
    end = parse_minute(changes["end"]) if "end" in changes else rule.end_minute
    try:
        check_windows([Window(start, end)])
    except ValueError as exc:
        raise Invalid(str(exc)) from exc
    async with _no_overlap(session, weekday):
        rule.weekday, rule.start_minute, rule.end_minute = weekday, start, end
    await enqueue_replan(session, user_id=user_id, trigger="availability")
    await session.commit()
    return rule


async def delete_rule(session: AsyncSession, rule_id: uuid.UUID, *, user_id: uuid.UUID) -> None:
    rule = await get_rule(session, rule_id, user_id=user_id)
    await session.delete(rule)
    await enqueue_replan(session, user_id=user_id, trigger="availability")
    await session.commit()


# --- exceptions ------------------------------------------------------------------------


def _stored(windows: list[WindowIn]) -> list[dict[str, int]]:
    ordered = check_windows(window.minutes() for window in windows)
    return [{"start": w.start, "end": w.end} for w in ordered]


@asynccontextmanager
async def _one_per_date(session: AsyncSession, day: date) -> AsyncIterator[None]:
    try:
        async with session.begin_nested():
            yield
            await session.flush()
    except IntegrityError as exc:
        if "uq_availability_exceptions_date" not in str(exc.orig):
            raise
        raise Conflict(f"{day.isoformat()} already has an exception.") from exc


async def list_exceptions(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    first: date | None = None,
    last: date | None = None,
) -> list[AvailabilityException]:
    query = select(AvailabilityException).where(AvailabilityException.user_id == user_id)
    if first is not None:
        query = query.where(AvailabilityException.date >= first)
    if last is not None:
        query = query.where(AvailabilityException.date <= last)
    return list(await session.scalars(query.order_by(AvailabilityException.date)))


async def get_exception(
    session: AsyncSession, exception_id: uuid.UUID, *, user_id: uuid.UUID
) -> AvailabilityException:
    found = await session.scalar(
        select(AvailabilityException).where(
            AvailabilityException.id == exception_id, AvailabilityException.user_id == user_id
        )
    )
    if found is None:
        raise NotFound("Availability exception")
    return found


async def create_exception(
    session: AsyncSession, data: ExceptionCreate, *, user_id: uuid.UUID
) -> AvailabilityException:
    exception = AvailabilityException(
        user_id=user_id,
        date=data.date,
        unavailable=data.unavailable,
        windows=_stored(data.windows),
        note=data.note or None,
    )
    async with _one_per_date(session, data.date):
        session.add(exception)
    await enqueue_replan(session, user_id=user_id, trigger="availability")
    await session.commit()
    return exception


async def update_exception(
    session: AsyncSession, exception_id: uuid.UUID, data: ExceptionUpdate, *, user_id: uuid.UUID
) -> AvailabilityException:
    exception = await get_exception(session, exception_id, user_id=user_id)
    changes = data.model_dump(exclude_unset=True)
    unavailable = changes.get("unavailable", exception.unavailable)
    if data.windows is not None:
        windows = _stored(data.windows)
    elif unavailable:
        windows = []  # marking a day unavailable drops its windows
    else:
        windows = exception.windows
    if unavailable == bool(windows):
        raise Invalid(
            "An unavailable day has no windows."
            if unavailable
            else "Add at least one window, or mark the day unavailable."
        )
    day = changes.get("date", exception.date)
    async with _one_per_date(session, day):
        exception.date, exception.unavailable, exception.windows = day, unavailable, windows
        if "note" in changes:
            exception.note = changes["note"] or None
    await enqueue_replan(session, user_id=user_id, trigger="availability")
    await session.commit()
    return exception


async def delete_exception(
    session: AsyncSession, exception_id: uuid.UUID, *, user_id: uuid.UUID
) -> None:
    exception = await get_exception(session, exception_id, user_id=user_id)
    await session.delete(exception)
    await enqueue_replan(session, user_id=user_id, trigger="availability")
    await session.commit()


def window_out(start: int, end: int) -> dict[str, str]:
    return {"start": format_minute(start), "end": format_minute(end)}


# --- expanded availability -------------------------------------------------------------


async def availability(
    session: AsyncSession, first: date, last: date, *, user_id: uuid.UUID
) -> tuple[User, list[Day], int]:
    """The user, each date's free time from ``first`` to ``last`` (local dates, inclusive),
    and a typical week from the rules alone. At most 62 days at a time."""
    if last < first:
        raise Invalid("The range ends before it starts.")
    if last - first >= timedelta(days=MAX_RANGE_DAYS):
        raise Invalid(f"Ask for at most {MAX_RANGE_DAYS} days at a time.")
    user = await _user(session, user_id)
    rules = [
        Rule(r.weekday, Window(r.start_minute, r.end_minute))
        for r in await list_rules(session, user_id=user_id)
    ]
    exceptions = {
        e.date: DayException(e.unavailable, tuple(Window(w["start"], w["end"]) for w in e.windows))
        for e in await list_exceptions(session, user_id=user_id, first=first, last=last)
    }
    days = expand(
        rules, exceptions, first, last, ZoneInfo(user.timezone), user.daily_study_cap_minutes
    )
    return user, days, weekly_minutes(rules, user.daily_study_cap_minutes)


# --- a topic's workload and confidence -------------------------------------------------


async def page_kinds(
    session: AsyncSession,
    module_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
    topic_id: uuid.UUID | None = None,
) -> dict[uuid.UUID, tuple[int, int]]:
    """Distinct pages linked to each topic, as (slide pages, text pages). Pages of other
    kinds (past papers, tests, assignments, outlines) aren't counted."""
    page = func.concat(Chunk.material_id, literal(":"), Chunk.page_number)
    query = (
        select(ChunkTopic.topic_id, Material.kind, func.count(func.distinct(page)))
        .join(Chunk, (Chunk.id == ChunkTopic.chunk_id) & (Chunk.module_id == ChunkTopic.module_id))
        .join(Material, (Material.id == Chunk.material_id) & (Material.user_id == user_id))
        .where(
            ChunkTopic.module_id == module_id,
            Chunk.user_id == user_id,
            Material.kind.in_(SLIDE_KINDS + TEXT_KINDS),
        )
        .group_by(ChunkTopic.topic_id, Material.kind)
    )
    if topic_id is not None:
        query = query.where(ChunkTopic.topic_id == topic_id)
    counts: dict[uuid.UUID, tuple[int, int]] = {}
    for found_topic, kind, count in await session.execute(query):
        slides, text = counts.get(found_topic, (0, 0))
        if kind in SLIDE_KINDS:
            slides += int(count)
        else:
            text += int(count)
        counts[found_topic] = (slides, text)
    return counts


async def topic_pages(
    session: AsyncSession, module_id: uuid.UUID, *, user_id: uuid.UUID
) -> dict[uuid.UUID, set[Page]]:
    """The distinct pages linked to each topic in the module, as (material, page, is a slide),
    for slide and text kinds only (decision 0016)."""
    query = (
        select(ChunkTopic.topic_id, Chunk.material_id, Chunk.page_number, Material.kind)
        .distinct()
        .join(Chunk, (Chunk.id == ChunkTopic.chunk_id) & (Chunk.module_id == ChunkTopic.module_id))
        .join(Material, (Material.id == Chunk.material_id) & (Material.user_id == user_id))
        .where(
            ChunkTopic.module_id == module_id,
            Chunk.user_id == user_id,
            Material.kind.in_(SLIDE_KINDS + TEXT_KINDS),
        )
    )
    out: dict[uuid.UUID, set[Page]] = {}
    for topic_id, material_id, page_number, kind in await session.execute(query):
        out.setdefault(topic_id, set()).add((material_id, page_number, kind in SLIDE_KINDS))
    return out


def topic_tree(topics: list[Topic]) -> Tree:
    """The planning tree of a module's topics, given in sibling order (``list_topics``)."""
    return make_tree([(t.id, t.parent_id) for t in topics])


async def topic_workloads(
    session: AsyncSession, module_id: uuid.UUID, topics: list[Topic], *, user_id: uuid.UUID
) -> tuple[dict[uuid.UUID, Workload], dict[uuid.UUID, SubtreeWorkload]]:
    """Each topic's own workload, and for each topic with subtopics the workload of its whole
    subtree (decision 0019: the planner's figure when the topic is ticked in an assessment).
    ``topics`` is the module's whole list, in sibling order."""
    await get_module(session, module_id, user_id=user_id)
    pages = await topic_pages(session, module_id, user_id=user_id)
    tree = topic_tree(topics)
    own: dict[uuid.UUID, Workload] = {}
    whole: dict[uuid.UUID, SubtreeWorkload] = {}
    for t in topics:
        linked = pages.get(t.id, set())
        slides = sum(1 for page in linked if page[2])
        own[t.id] = workload(t.estimated_minutes, slides, len(linked) - slides)
        if tree.children.get(t.id):
            whole[t.id] = subtree_workload(tree, t.id, t.estimated_minutes, pages)
    return own, whole


async def update_topic_planning(
    session: AsyncSession, topic_id: uuid.UUID, data: TopicPlanningUpdate, *, user_id: uuid.UUID
) -> tuple[Topic, Workload]:
    topic = await get_topic(session, topic_id, user_id=user_id)
    for name, value in data.model_dump(exclude_unset=True).items():
        setattr(topic, name, value)
    await enqueue_replan(
        session, user_id=user_id, trigger="topic", detail={"module_id": str(topic.module_id)}
    )
    await session.commit()
    kinds = await page_kinds(session, topic.module_id, user_id=user_id, topic_id=topic.id)
    return topic, workload(topic.estimated_minutes, *kinds.get(topic.id, (0, 0)))
