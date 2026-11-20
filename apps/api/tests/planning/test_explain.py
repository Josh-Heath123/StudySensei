"""The plan in words (decision 0018): each reason's text, the labels on every number, and the
feasibility report's lines. Nothing is stated that the inputs don't contain."""

import re
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from app.services.planning import explain
from app.services.planning.feasibility import (
    AssessmentFeasibility,
    Feasibility,
    Lever,
    Numbers,
)
from app.services.planning.inputs import AssessmentFacts, ModuleFacts, PlanFacts, TopicFacts
from app.services.planning.planner import Block, BlockKind, Reason, Shortfall

SAST = ZoneInfo("Africa/Johannesburg")
MODULE, TEST, TOPIC = UUID(int=1), UUID(int=2), UUID(int=3)
# The block is on Thursday 26 Nov; the test is on Wednesday 2 Dec: 6 days later.
BLOCK_START = datetime(2026, 11, 26, 18, 0, tzinfo=SAST)
DUE = datetime(2026, 12, 2, 9, 0, tzinfo=SAST)

ESTIMATED = TopicFacts(
    name="Microservices",
    confidence=None,
    workload_minutes=40,
    workload_source="estimated",
    slide_pages=13,
    text_pages=0,
    studied_minutes=15,
    sessions=1,
)


def facts(topic: TopicFacts = ESTIMATED, weight: float | None = 30) -> PlanFacts:
    return PlanFacts(
        timezone=SAST,
        daily_cap_minutes=180,
        first=BLOCK_START.date(),
        last=DUE.date(),
        modules={MODULE: ModuleFacts("COS330", "#3D7BFF")},
        assessments={TEST: AssessmentFacts("Test 2", MODULE, DUE, weight)},
        topics={TOPIC: topic},
        later=(),
    )


def block(reason: Reason, start: datetime = BLOCK_START) -> Block:
    kind: BlockKind = "review" if reason == "final_review" else "study"
    topic = None if kind == "review" else TOPIC
    return Block(start, start + timedelta(minutes=50), MODULE, TEST, topic, kind, reason)


# --- each reason -----------------------------------------------------------------------


def test_urgency() -> None:
    assert explain.reason_text(block("urgency"), facts()) == (
        "COS330 Test 2 is in 6 days (30 % of the module). "
        "≈ 40 min estimated from 13 slides; 15 min studied so far (measured, 1 session)."
    )


@pytest.mark.parametrize(
    ("days_before", "words"), [(0, "is today"), (1, "is tomorrow"), (2, "is in 2 days")]
)
def test_urgency_counts_local_days(days_before: int, words: str) -> None:
    start = DUE.replace(hour=7) - timedelta(days=days_before)
    assert explain.urgency_sentence(block("urgency", start), facts()).startswith(
        f"COS330 Test 2 {words}"
    )


def test_urgency_without_a_weight_says_nothing_about_weight() -> None:
    text = explain.urgency_sentence(block("urgency"), facts(weight=None))
    assert text == "COS330 Test 2 is in 6 days."


def test_low_confidence() -> None:
    rated = replace(ESTIMATED, confidence=2)
    assert explain.reason_text(block("low_confidence"), facts(rated)).startswith(
        "You rated this 2 of 5, so it gets 25 % more time. "
    )
    one = replace(ESTIMATED, confidence=1)
    assert "1 of 5, so it gets 50 % more time" in explain.reason_text(
        block("low_confidence"), facts(one)
    )


def test_no_estimate() -> None:
    assert explain.reason_text(block("no_estimate"), facts()) == (
        "No slides or pages are linked yet, so it gets two blocks by default. "
        "Set your own time in the topic."
    )


def test_workload() -> None:
    assert explain.reason_text(block("workload"), facts()) == (
        "≈ 40 min estimated from 13 slides; 15 min studied so far (measured, 1 session)."
    )


def test_spacing() -> None:
    assert explain.reason_text(block("spacing"), facts()) == (
        "A second day on this topic helps it stick."
    )


def test_final_review() -> None:
    assert explain.reason_text(block("final_review"), facts()) == (
        "The last free time before COS330 Test 2: a mixed review of its topics."
    )


# --- labels ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("topic", "sentence"),
    [
        (
            replace(ESTIMATED, workload_source="yours", workload_minutes=90),
            "1 h 30 by your own figure; 15 min studied so far (measured, 1 session).",
        ),
        (
            replace(ESTIMATED, slide_pages=0, text_pages=4, workload_minutes=25),
            "≈ 25 min estimated from 4 pages of text; 15 min studied so far (measured, 1 session).",
        ),
        (
            replace(ESTIMATED, slide_pages=1, text_pages=1, workload_minutes=10),
            "≈ 10 min estimated from 1 slide and 1 page of text; "
            "15 min studied so far (measured, 1 session).",
        ),
        (
            replace(ESTIMATED, studied_minutes=0, sessions=0),
            "≈ 40 min estimated from 13 slides; not studied yet (measured: no sessions).",
        ),
        (
            replace(ESTIMATED, studied_minutes=125, sessions=3),
            "≈ 40 min estimated from 13 slides; 2 h 05 studied so far (measured, 3 sessions).",
        ),
    ],
)
def test_every_minute_figure_says_where_it_came_from(topic: TopicFacts, sentence: str) -> None:
    assert explain.workload_sentence(topic) == sentence


@pytest.mark.parametrize("reason", ["urgency", "low_confidence", "workload"])
def test_every_study_reason_labels_its_minutes(reason: Reason) -> None:
    rated = replace(ESTIMATED, confidence=1)
    text = explain.reason_text(block(reason), facts(rated))
    # Every "N min" or "N h" figure is followed, in its clause, by its basis.
    for clause in text.split(";"):
        if re.search(r"\d+ (min|h)", clause):
            assert re.search(r"estimated|your own figure|measured", clause), clause


@pytest.mark.parametrize(
    ("minutes", "text"),
    [(0, "0 min"), (40, "40 min"), (60, "1 h"), (65, "1 h 05"), (180, "3 h"), (250, "4 h 10")],
)
def test_durations(minutes: int, text: str) -> None:
    assert explain.duration(minutes) == text


# --- the feasibility report ------------------------------------------------------------


@pytest.mark.parametrize(
    ("shortfall", "text"),
    [
        (
            Shortfall("not_enough_time", TEST, TOPIC, 250, 180),
            "Microservices: needs 4 h 10, 3 h planned: 1 h 10 short.",
        ),
        (
            Shortfall("not_enough_time", TEST, TOPIC, 100, 0),
            "Microservices: needs 1 h 40, nothing planned: 1 h 40 short.",
        ),
        (
            Shortfall("not_spaced", TEST, TOPIC, 100, 50),
            "Microservices: all its blocks are on one day; a second day would help it stick.",
        ),
        (
            Shortfall("not_spaced", TEST, TOPIC, 100, 0),
            "Microservices: no block fits before the deadline.",
        ),
        (
            Shortfall("no_estimate", TEST, TOPIC, 100, 100),
            "Microservices: no slides or pages are linked, so it gets two blocks by default. "
            "Set your own time in the topic.",
        ),
        (
            Shortfall("no_review_time", TEST),
            "No free time for a final review in the 3 days before it.",
        ),
        (
            Shortfall("no_topics", TEST),
            "COS330 Test 2 covers no topics yet: add them in its Assessments tab.",
        ),
    ],
)
def test_each_shortfall_in_words(shortfall: Shortfall, text: str) -> None:
    assert explain.shortfall_text(shortfall, facts()) == text


def numbers(**fields: object) -> Numbers:
    base = Numbers(
        required_minutes=840,
        planned_minutes=540,
        short_minutes=300,
        review_minutes=50,
        free_minutes=540,
        booked_minutes=540,
        status="short",
    )
    return replace(base, **fields)  # type: ignore[arg-type]


def test_the_overall_line() -> None:
    report = Feasibility((), numbers(), datetime(2026, 12, 3, 9, 0, tzinfo=SAST), ())
    assert explain.overall_line(report, facts(), 28) == "You need 14 h before 3 Dec and have 9 h."


def test_the_overall_line_with_nothing_due() -> None:
    report = Feasibility((), numbers(required_minutes=0, free_minutes=0), None, ())
    assert explain.overall_line(report, facts(), 28) == "Nothing is due in the next 28 days."


@pytest.mark.parametrize(
    ("fields", "ending"),
    [
        ({}, "short by 5 h."),
        ({"short_minutes": 0, "status": "tight"}, "tight."),
        ({"short_minutes": 0, "status": "fits"}, "fits."),
    ],
)
def test_an_assessments_line(fields: dict[str, object], ending: str) -> None:
    report = AssessmentFeasibility(TEST, DUE, numbers(**fields), (), ())
    assert explain.assessment_line(report, facts()) == (
        f"COS330 Test 2 (2 Dec): needs 14 h, 9 h planned, 9 h free before it: {ending}"
    )


def test_levers_are_plain_options() -> None:
    f = facts()
    assert explain.lever_text(Lever("add_time"), f) == (
        "Add study time: more weekly hours, or fewer days off, in Settings → Study time."
    )
    assert explain.lever_text(Lever("raise_cap"), f) == (
        "Raise the daily cap (now 3 h) in Settings → Study time."
    )
    assert explain.lever_text(Lever("narrow_topics", TEST), f) == (
        "Narrow COS330 Test 2's topics to what it really covers, in its Assessments tab."
    )


def test_a_later_assessment() -> None:
    assert explain.later_text(TEST, facts(), 3) == (
        "COS330 Test 2 is due 2 Dec, after these 3 days: it isn't planned yet."
    )


# --- units with subtopics (decision 0019) ----------------------------------------------

CHAPTER = replace(
    ESTIMATED,
    name="Ch1",
    workload_minutes=435,
    slide_pages=72,
    text_pages=34,
    subtopics=4,
)


def test_a_units_workload_names_its_subtopics() -> None:
    assert explain.reason_text(block("workload"), facts(CHAPTER)) == (
        "≈ 7 h 15 estimated from 72 slides and 34 pages of text across Ch1 and its "
        "4 subtopics; 15 min studied so far (measured, 1 session)."
    )
    one = replace(CHAPTER, subtopics=1)
    assert "across Ch1 and its 1 subtopic;" in explain.workload_sentence(one)
    yours = replace(CHAPTER, workload_source="yours", workload_minutes=600)
    assert explain.workload_sentence(yours).startswith(
        "10 h by your own figure for Ch1 and its subtopics; "
    )


def test_confidence_from_the_subtopics_says_so() -> None:
    rated = replace(CHAPTER, confidence=2, confidence_source="subtopics")
    assert explain.reason_text(block("low_confidence"), facts(rated)).startswith(
        "You rated its subtopics 2 of 5 on average, so it gets 25 % more time. "
    )


def test_no_estimate_for_a_unit_with_subtopics() -> None:
    empty = replace(CHAPTER, workload_minutes=None, workload_source="none")
    assert explain.reason_text(block("no_estimate"), facts(empty)) == (
        "No slides or pages are linked to it or its subtopics yet, so it gets two blocks "
        "by default. Set your own time in the topic."
    )


def test_an_assessment_whose_topics_are_planned_for_a_sooner_one() -> None:
    sooner = UUID(int=7)
    f = facts()
    both = replace(
        f,
        assessments={
            **f.assessments,
            sooner: AssessmentFacts("Semester test", MODULE, DUE - timedelta(days=2), None),
        },
    )
    zero = numbers(required_minutes=0, planned_minutes=0, short_minutes=0, status="fits")
    report = AssessmentFeasibility(TEST, DUE, zero, (), (), planned_with=(sooner,))
    assert explain.assessment_line(report, both) == (
        "COS330 Test 2 (2 Dec): its topics are planned for COS330 Semester test (30 Nov)."
    )
    done = AssessmentFeasibility(TEST, DUE, zero, (), (), all_done=True)
    assert "needs" not in explain.assessment_line(done, f)
