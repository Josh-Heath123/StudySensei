"""The plan in words (decision 0018): one or two short sentences per block, and the
feasibility report's lines. Pure, and written by code from computed facts: no AI.

Rules for every sentence:
- it states only what the inputs contain (a missing weight is left out, not guessed);
- minutes of work are labelled: "estimated" (from linked pages), "your own figure", or
  "measured" (from sessions, with how many);
- durations are "40 min", "3 h" or "4 h 10".
"""

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from app.services.planning.feasibility import AssessmentFeasibility, Feasibility, Lever, Numbers
from app.services.planning.inputs import PlanFacts, TopicFacts
from app.services.planning.planner import (
    CONFIDENCE_PERCENT,
    REVIEW_DAYS,
    Block,
    Shortfall,
)

BASIS = (
    "Needed time is estimated: each topic's workload (your own figure, or estimated from its "
    "pages), less the time measured in your sessions, adjusted for your confidence. Free time "
    "is your study time, at most the daily cap each day."
)

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def duration(minutes: int) -> str:
    """40 → "40 min"; 180 → "3 h"; 250 → "4 h 10"; 65 → "1 h 05"."""
    if minutes < 60:
        return f"{minutes} min"
    hours, rest = divmod(minutes, 60)
    return f"{hours} h" if rest == 0 else f"{hours} h {rest:02d}"


def percent(value: float) -> str:
    """30.0 → "30 %"; 12.5 → "12.5 %"."""
    return f"{value:g} %"


def plural(count: int, word: str, words: str | None = None) -> str:
    return f"{count} {word if count == 1 else (words or word + 's')}"


def day_month(at: datetime, facts: PlanFacts) -> str:
    """The local date, like "3 Dec"."""
    local = at.astimezone(facts.timezone)
    return f"{local.day} {MONTHS[local.month - 1]}"


def assessment_name(assessment_id: UUID, facts: PlanFacts) -> str:
    """ "COS330 Semester test 2" (the module code, then the title)."""
    assessment = facts.assessments[assessment_id]
    module = facts.modules.get(assessment.module_id)
    return f"{module.code} {assessment.title}" if module else assessment.title


def topic_name(topic_id: UUID, facts: PlanFacts) -> str:
    topic = facts.topics.get(topic_id)
    return topic.name if topic else "A topic"


# --- blocks ----------------------------------------------------------------------------


def _pages(topic: TopicFacts) -> str:
    parts = []
    if topic.slide_pages:
        parts.append(plural(topic.slide_pages, "slide"))
    if topic.text_pages:
        parts.append(plural(topic.text_pages, "page") + " of text")
    return " and ".join(parts)


def _across(topic: TopicFacts) -> str:
    """ " across Ch1 and its 4 subtopics" for a unit with subtopics (decision 0019), else ""."""
    if topic.subtopics == 0:
        return ""
    return f" across {topic.name} and its {plural(topic.subtopics, 'subtopic')}"


def workload_sentence(topic: TopicFacts) -> str:
    """ "≈ 40 min estimated from 13 slides; 15 min studied so far (measured, 1 session)." For
    a topic with subtopics: "≈ 7 h estimated from 72 slides and 34 pages of text across Ch1
    and its 4 subtopics; ..." """
    if topic.workload_minutes is None:
        load = "No workload figure yet"
    elif topic.workload_source == "yours":
        whole = f" for {topic.name} and its subtopics" if topic.subtopics else ""
        load = f"{duration(topic.workload_minutes)} by your own figure{whole}"
    else:
        load = (
            f"≈ {duration(topic.workload_minutes)} estimated from {_pages(topic)}{_across(topic)}"
        )
    if topic.sessions == 0:
        studied = "not studied yet (measured: no sessions)"
    elif topic.studied_minutes == 0:
        studied = f"under 1 min studied so far (measured, {plural(topic.sessions, 'session')})"
    else:
        studied = (
            f"{duration(topic.studied_minutes)} studied so far "
            f"(measured, {plural(topic.sessions, 'session')})"
        )
    return f"{load}; {studied}."


def urgency_sentence(block: Block, facts: PlanFacts) -> str:
    """ "COS330 Test 2 is in 6 days (30 % of the module)." Days count from the block's local
    date to the deadline's."""
    assessment = facts.assessments[block.assessment_id]
    tz = facts.timezone
    days = (assessment.due_at.astimezone(tz).date() - block.start.astimezone(tz).date()).days
    when = "is today" if days <= 0 else "is tomorrow" if days == 1 else f"is in {days} days"
    weight = "" if assessment.weight is None else f" ({percent(assessment.weight)} of the module)"
    return f"{assessment_name(block.assessment_id, facts)} {when}{weight}."


def reason_text(block: Block, facts: PlanFacts) -> str:
    """One or two short sentences on why this block is here, from its reason and facts."""
    if block.reason == "final_review":
        name = assessment_name(block.assessment_id, facts)
        return f"The last free time before {name}: a mixed review of its topics."
    if block.reason == "spacing":
        return "A second day on this topic helps it stick."
    topic = facts.topics.get(block.topic_id) if block.topic_id else None
    if block.reason == "no_estimate":
        where = "to it or its subtopics " if topic and topic.subtopics else ""
        return (
            f"No slides or pages are linked {where}yet, so it gets two blocks by default. "
            "Set your own time in the topic."
        )
    if topic is None:
        return urgency_sentence(block, facts)
    if block.reason == "low_confidence" and topic.confidence is not None:
        extra = CONFIDENCE_PERCENT[topic.confidence] - 100
        rated = (
            f"You rated its subtopics {topic.confidence} of 5 on average"
            if topic.confidence_source == "subtopics"
            else f"You rated this {topic.confidence} of 5"
        )
        return f"{rated}, so it gets {extra} % more time. " + workload_sentence(topic)
    if block.reason == "urgency":
        return f"{urgency_sentence(block, facts)} {workload_sentence(topic)}"
    return workload_sentence(topic)


# --- the feasibility report ------------------------------------------------------------


def shortfall_text(shortfall: Shortfall, facts: PlanFacts) -> str:
    """One shortfall in words."""
    topic = topic_name(shortfall.topic_id, facts) if shortfall.topic_id else ""
    if shortfall.kind == "not_enough_time":
        need, got = shortfall.required_minutes, shortfall.scheduled_minutes
        planned = f"{duration(got)} planned" if got else "nothing planned"
        return f"{topic}: needs {duration(need)}, {planned}: {duration(need - got)} short."
    if shortfall.kind == "not_spaced":
        if shortfall.scheduled_minutes == 0:
            return f"{topic}: no block fits before the deadline."
        return f"{topic}: all its blocks are on one day; a second day would help it stick."
    if shortfall.kind == "no_estimate":
        found = facts.topics.get(shortfall.topic_id) if shortfall.topic_id else None
        where = " to it or its subtopics" if found and found.subtopics else ""
        return (
            f"{topic}: no slides or pages are linked{where}, so it gets two blocks by "
            "default. Set your own time in the topic."
        )
    if shortfall.kind == "no_review_time":
        return f"No free time for a final review in the {REVIEW_DAYS} days before it."
    return (
        f"{assessment_name(shortfall.assessment_id, facts)} covers no topics yet: "
        "add them in its Assessments tab."
    )


def status_words(numbers: Numbers) -> str:
    if numbers.status == "short":
        return f"short by {duration(numbers.short_minutes)}"
    if numbers.status == "tight":
        return "tight"
    return "fits"


def assessment_line(report: AssessmentFeasibility, facts: PlanFacts) -> str:
    """ "COS330 Test 2 (3 Dec): needs 4 h 10, 3 h planned, 9 h free before it: short by
    1 h 10." When its topics are all planned for sooner assessments, it says so instead."""
    n = report.numbers
    name = assessment_name(report.assessment_id, facts)
    when = day_month(report.due_at, facts)
    if report.planned_with:
        others = " and ".join(
            f"{assessment_name(other, facts)} ({day_month(facts.assessments[other].due_at, facts)})"
            for other in report.planned_with
        )
        return f"{name} ({when}): its topics are planned for {others}."
    if report.all_done:
        return f"{name} ({when}): its topics need no more time (measured study covers them)."
    return (
        f"{name} ({day_month(report.due_at, facts)}): needs {duration(n.required_minutes)}, "
        f"{duration(n.planned_minutes)} planned, {duration(n.free_minutes)} free before it: "
        f"{status_words(n)}."
    )


def overall_line(report: Feasibility, facts: PlanFacts, days: int) -> str:
    """ "You need 14 h before 3 Dec and have 9 h." With nothing needed: "Nothing more is
    needed before 26 Nov; you have 21 h free." When it's short though the time would cover
    it (the time is in the wrong place), the short assessments are named (decision 0020)."""
    if report.last_deadline is None:
        return f"Nothing is due in the next {plural(days, 'day')}."
    need, have = report.overall.required_minutes, report.overall.free_minutes
    before = day_month(report.last_deadline, facts)
    if need == 0:
        return f"Nothing more is needed before {before}; you have {duration(have)} free."
    line = f"You need {duration(need)} before {before} and have {duration(have)}"
    short = [a for a in report.assessments if a.numbers.status == "short"]
    if report.overall.status == "short" and need <= have and short:
        if len(short) == 1:
            only = short[0]
            name = assessment_name(only.assessment_id, facts)
            when = day_month(only.due_at, facts)
            return f"{line}, but {name} ({when}) is {duration(only.numbers.short_minutes)} short."
        return f"{line}, but {len(short)} assessments are short."
    return f"{line}."


def lever_text(lever: Lever, facts: PlanFacts) -> str:
    if lever.kind == "add_time":
        return "Add study time: more weekly hours, or fewer days off, in Settings → Study time."
    if lever.kind == "raise_cap":
        return (
            f"Raise the daily cap (now {duration(facts.daily_cap_minutes)}) "
            "in Settings → Study time."
        )
    name = assessment_name(lever.assessment_id, facts) if lever.assessment_id else "an assessment"
    return f"Narrow {name}'s topics to what it really covers, in its Assessments tab."


def later_text(assessment_id: UUID, facts: PlanFacts, days: int) -> str:
    """ "COS330 Exam is due 5 Jan, after these 28 days: it isn't planned yet." """
    due = facts.assessments[assessment_id].due_at
    return (
        f"{assessment_name(assessment_id, facts)} is due {day_month(due, facts)}, after these "
        f"{plural(days, 'day')}: it isn't planned yet."
    )


# --- plan versions (decision 0021) -----------------------------------------------------

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def block_when(start: datetime, timezone: ZoneInfo) -> str:
    """ "Tue 24 Nov, 18:00" in local time."""
    local = start.astimezone(timezone)
    return f"{WEEKDAYS[local.weekday()]} {local.day} {MONTHS[local.month - 1]}, {local:%H:%M}"


def version_summary(
    trigger: str,
    *,
    timezone: ZoneInfo,
    block_name: str | None = None,
    block_start: datetime | None = None,
    minutes: int | None = None,
    assessment: str | None = None,
    module: str | None = None,
) -> str:
    """One sentence on why a plan version exists, from its trigger and what it names. A
    missing name falls back to a general sentence; nothing is guessed."""
    if trigger == "skip" and block_name and block_start:
        when = block_when(block_start, timezone)
        return f"You skipped {block_name} ({when}): its time is placed again."
    if trigger == "skip":
        return "You skipped a block: its time is placed again."
    if trigger == "finish" and block_name:
        measured = (
            ""
            if minutes is None
            else " (measured under 1 min)"
            if minutes == 0
            else f" (measured {duration(minutes)})"
        )
        return f"You finished a block on {block_name}{measured}."
    if trigger == "finish":
        return "You finished a block."
    if trigger == "assessment":
        return f"{assessment} changed." if assessment else "An assessment changed."
    if trigger == "topic":
        return f"A topic in {module} changed." if module else "A topic changed."
    if trigger == "availability":
        return "Your study time changed."
    if trigger == "material":
        return (
            f"New material was processed for {module}." if module else "New material was processed."
        )
    if trigger == "nightly":
        return "Updated overnight."
    if trigger == "manual":
        return "Re-planned on request."
    return "Your first plan."
