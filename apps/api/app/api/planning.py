"""Planning inputs: settings, weekly availability and its exceptions, per-topic workload and
confidence, and the plan preview. Thin: the services in ``app/services/planning/`` do the work."""

import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser
from app.core.db import SessionDep
from app.models import AvailabilityException, AvailabilityRule
from app.schemas.academics import WorkloadOut
from app.schemas.planning import (
    MAX_RANGE_DAYS,
    AvailabilityDayOut,
    AvailabilityOut,
    ExceptionCreate,
    ExceptionOut,
    ExceptionUpdate,
    IntervalOut,
    PlanningSettingsOut,
    PlanningSettingsUpdate,
    PlanPreviewOut,
    RuleCreate,
    RuleOut,
    RuleUpdate,
    TopicPlanningOut,
    TopicPlanningUpdate,
    WindowOut,
)
from app.services.planning import store
from app.services.planning.availability import format_minute
from app.services.planning.inputs import DEFAULT_DAYS
from app.services.planning.preview import preview

router = APIRouter(tags=["planning"])


def _rule_out(rule: AvailabilityRule) -> RuleOut:
    return RuleOut(
        id=rule.id,
        weekday=rule.weekday,
        start=format_minute(rule.start_minute),
        end=format_minute(rule.end_minute),
    )


def _exception_out(exception: AvailabilityException) -> ExceptionOut:
    return ExceptionOut(
        id=exception.id,
        date=exception.date,
        unavailable=exception.unavailable,
        windows=[
            WindowOut(start=format_minute(w["start"]), end=format_minute(w["end"]))
            for w in exception.windows
        ],
        note=exception.note,
    )


# --- settings --------------------------------------------------------------------------


@router.get("/planning/settings", response_model=PlanningSettingsOut)
async def get_planning_settings(session: SessionDep, user: CurrentUser) -> PlanningSettingsOut:
    """The timezone availability is written in, and the most study time a day."""
    found = await store.get_settings(session, user_id=user.id)
    return PlanningSettingsOut.model_validate(found)


@router.patch("/planning/settings", response_model=PlanningSettingsOut)
async def update_planning_settings(
    data: PlanningSettingsUpdate, session: SessionDep, user: CurrentUser
) -> PlanningSettingsOut:
    """Change the timezone (IANA) or the daily cap (15 to 1,440 minutes)."""
    updated = await store.update_settings(session, data, user_id=user.id)
    return PlanningSettingsOut.model_validate(updated)


# --- weekly rules ----------------------------------------------------------------------


@router.get("/availability/rules", response_model=list[RuleOut])
async def list_rules(session: SessionDep, user: CurrentUser) -> list[RuleOut]:
    """Weekly windows, by weekday (0 is Monday) then start."""
    return [_rule_out(rule) for rule in await store.list_rules(session, user_id=user.id)]


@router.post("/availability/rules", response_model=RuleOut, status_code=status.HTTP_201_CREATED)
async def create_rule(data: RuleCreate, session: SessionDep, user: CurrentUser) -> RuleOut:
    """A weekly window, "HH:MM" to "HH:MM" local time ("24:00" ends at midnight). 409 if
    it overlaps another window that weekday."""
    return _rule_out(await store.create_rule(session, data, user_id=user.id))


@router.patch("/availability/rules/{rule_id}", response_model=RuleOut)
async def update_rule(
    rule_id: uuid.UUID, data: RuleUpdate, session: SessionDep, user: CurrentUser
) -> RuleOut:
    return _rule_out(await store.update_rule(session, rule_id, data, user_id=user.id))


@router.delete("/availability/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(rule_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> None:
    await store.delete_rule(session, rule_id, user_id=user.id)


# --- exceptions ------------------------------------------------------------------------


@router.get("/availability/exceptions", response_model=list[ExceptionOut])
async def list_exceptions(
    session: SessionDep,
    user: CurrentUser,
    first: Annotated[date | None, Query(alias="from")] = None,
    last: Annotated[date | None, Query(alias="to")] = None,
) -> list[ExceptionOut]:
    """Exceptions by date, optionally from and to a local date (inclusive)."""
    found = await store.list_exceptions(session, user_id=user.id, first=first, last=last)
    return [_exception_out(exception) for exception in found]


@router.post(
    "/availability/exceptions", response_model=ExceptionOut, status_code=status.HTTP_201_CREATED
)
async def create_exception(
    data: ExceptionCreate, session: SessionDep, user: CurrentUser
) -> ExceptionOut:
    """One date that doesn't follow the rules: ``unavailable``, or its own ``windows``.
    409 if that date already has one."""
    return _exception_out(await store.create_exception(session, data, user_id=user.id))


@router.patch("/availability/exceptions/{exception_id}", response_model=ExceptionOut)
async def update_exception(
    exception_id: uuid.UUID, data: ExceptionUpdate, session: SessionDep, user: CurrentUser
) -> ExceptionOut:
    return _exception_out(
        await store.update_exception(session, exception_id, data, user_id=user.id)
    )


@router.delete("/availability/exceptions/{exception_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exception(exception_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> None:
    await store.delete_exception(session, exception_id, user_id=user.id)


# --- expanded --------------------------------------------------------------------------


@router.get("/availability", response_model=AvailabilityOut)
async def get_availability(
    session: SessionDep,
    user: CurrentUser,
    first: Annotated[date, Query(alias="from")],
    last: Annotated[date, Query(alias="to")],
) -> AvailabilityOut:
    """Each local date from ``from`` to ``to`` (inclusive, at most 62 days): its free
    intervals in UTC (exceptions over rules, DST-safe), free minutes, and the minutes
    available after the daily cap."""
    found, days, weekly = await store.availability(session, first, last, user_id=user.id)
    return AvailabilityOut(
        timezone=found.timezone,
        daily_study_cap_minutes=found.daily_study_cap_minutes,
        days=[
            AvailabilityDayOut(
                date=day.date,
                weekday=day.date.weekday(),
                source=day.source,
                intervals=[
                    IntervalOut(start=i.start, end=i.end, minutes=i.minutes) for i in day.intervals
                ],
                free_minutes=day.free_minutes,
                available_minutes=day.available_minutes,
            )
            for day in days
        ],
        total_free_minutes=sum(day.free_minutes for day in days),
        total_available_minutes=sum(day.available_minutes for day in days),
        weekly_minutes_from_rules=weekly,
    )


# --- a topic's workload and confidence -------------------------------------------------


@router.patch("/topics/{topic_id}/planning", response_model=TopicPlanningOut)
async def update_topic_planning(
    topic_id: uuid.UUID, data: TopicPlanningUpdate, session: SessionDep, user: CurrentUser
) -> TopicPlanningOut:
    """Set the topic's confidence (1 to 5, self-rated) or its workload in minutes (the
    student's own figure). Null clears either: "not rated", or back to the estimate."""
    topic, load = await store.update_topic_planning(session, topic_id, data, user_id=user.id)
    return TopicPlanningOut(
        topic_id=topic.id,
        confidence=topic.confidence,
        workload=WorkloadOut(
            minutes=load.minutes,
            source=load.source,
            slide_pages=load.slide_pages,
            text_pages=load.text_pages,
        ),
    )


# --- the plan preview ------------------------------------------------------------------


@router.get("/plan/preview", response_model=PlanPreviewOut)
async def preview_plan(
    session: SessionDep,
    user: CurrentUser,
    days: Annotated[int, Query(ge=1, le=MAX_RANGE_DAYS)] = DEFAULT_DAYS,
) -> PlanPreviewOut:
    """The plan for the next ``days`` local dates (1 to 62, default 28), computed now and not
    stored: each block with its reason and study method in words (written by code, no AI),
    and the feasibility report per assessment and overall."""
    return await preview(session, user_id=user.id, now=datetime.now(UTC), days=days)
