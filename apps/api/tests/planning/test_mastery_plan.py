"""Mastery in the plan (ADR 0031): time, priority, the low_mastery reason, its text and the
methods. Without mastery every rule is the confidence rule it was (the other planner tests run
unchanged with mastery None)."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.services.planning import explain
from app.services.planning.availability import Interval
from app.services.planning.methods import BlockFacts, block_facts, choose
from app.services.planning.planner import (
    CONFIDENCE_PERCENT,
    Block,
    PlanInput,
    TopicInput,
    mastery_time_percent,
    plan,
    required_minutes,
    strength,
    strength_percent,
)
from tests.planning.plan_checks import check_plan
from tests.planning.test_explain import BLOCK_START, ESTIMATED, MODULE, TEST, TOPIC, facts
from tests.planning.test_plan_rules import NOW, UTC_ZONE, at, evenings, exam, make, topic


def unit(
    n: int,
    workload: int | None = 100,
    mastery: float | None = None,
    *,
    confidence: int | None = None,
    order: int = 0,
) -> TopicInput:
    return replace(topic(n, workload, confidence), mastery=mastery, order=order)


# --- time ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mastery", "percent"),
    [
        (0.0, 150),
        (0.1, 140),
        (0.34, 116),
        (0.5, 100),
        (0.6, 90),
        (0.79, 71),
        (0.8, 70),  # the lower clamp edge
        (0.95, 70),
        (1.0, 70),
    ],
)
def test_mastery_sets_the_percent_between_the_clamp_edges(mastery: float, percent: int) -> None:
    assert mastery_time_percent(mastery) == percent
    assert strength_percent(unit(1, mastery=mastery, confidence=5)) == percent


def test_the_percent_rounds_the_shown_mastery_half_up() -> None:
    # 0.345 shows as 35 % (34.5 rounds up), so the time is 150 - 35 = 115 %.
    assert mastery_time_percent(0.345) == 115
    assert mastery_time_percent(0.004) == 150  # 0 %, the upper clamp edge
    assert mastery_time_percent(0.796) == 70  # 80 %


def test_without_mastery_it_is_the_confidence_percent() -> None:
    for confidence in (None, 1, 2, 3, 4, 5):
        assert strength_percent(unit(1, confidence=confidence)) == CONFIDENCE_PERCENT.get(
            confidence or 3
        )


def test_mastery_wins_over_the_rating() -> None:
    # Rated 1 (150 %) but practised to 0.9: 70 %.
    assert required_minutes(unit(1, 100, mastery=0.9, confidence=1), 0) == 70
    # Rated 5 (70 %) but mastery 0.2: 130 %.
    assert required_minutes(unit(1, 100, mastery=0.2, confidence=5), 0) == 130


def test_a_weak_unit_gets_more_minutes() -> None:
    free = evenings(10)
    _, result = make(
        free=free,
        assessments=(exam(1, at(10, 9), 1, 2),),
        topics=(unit(1, 200, mastery=0.2), unit(2, 200, mastery=0.7)),
    )
    weak = sum(b.minutes for b in result.blocks if b.topic_id == UUID(int=1))
    strong = sum(b.minutes for b in result.blocks if b.topic_id == UUID(int=2))
    # Needed: 130 % and 80 % of 200; planned in whole blocks, at least that.
    assert [required_minutes(t, 0) for t in (unit(1, 200, 0.2), unit(2, 200, 0.7))] == [260, 160]
    assert (weak, strong) == (300, 200)


# --- priority ------------------------------------------------------------------------------


@given(
    st.lists(st.tuples(st.none() | st.integers(1, 5), st.integers(0, 20)), min_size=1, max_size=10)
)
def test_without_mastery_the_order_is_the_confidence_order(
    rated: list[tuple[int | None, int]],
) -> None:
    topics = [unit(i + 1, confidence=c, order=o) for i, (c, o) in enumerate(rated)]
    before = sorted(topics, key=lambda t: (t.confidence or 3, t.order, str(t.id)))
    after = sorted(topics, key=lambda t: (strength(t), t.order, str(t.id)))
    assert before == after


def test_strength_is_mastery_else_the_rating_else_a_half() -> None:
    assert strength(unit(1, mastery=0.3, confidence=5)) == 0.3
    assert strength(unit(1, confidence=1)) == 0.0
    assert strength(unit(1, confidence=4)) == 0.75
    assert strength(unit(1)) == 0.5


def first_order(result_blocks: tuple[Block, ...]) -> list[int]:
    order: list[int] = []
    for b in result_blocks:
        if b.topic_id is not None and b.topic_id.int not in order:
            order.append(b.topic_id.int)
    return order


def test_a_weak_unit_goes_first() -> None:
    # One block a day: the first block goes to the weaker unit, though it's later in the course.
    free = tuple(Interval(at(d, 18), at(d, 18, 50)) for d in range(1, 8))
    _, result = make(
        free=free,
        assessments=(exam(1, at(8, 9), 1, 2),),
        topics=(unit(1, 50, mastery=0.85, order=0), unit(2, 50, mastery=0.2, order=1)),
    )
    assert first_order(result.blocks) == [2, 1]


def test_mastery_and_a_rating_compare_on_one_scale() -> None:
    # Rated 2 is strength 0.25; mastery 0.3 is stronger, so the rated unit goes first.
    free = tuple(Interval(at(d, 18), at(d, 18, 50)) for d in range(1, 8))
    _, result = make(
        free=free,
        assessments=(exam(1, at(8, 9), 1, 2),),
        topics=(unit(1, 50, mastery=0.3, order=0), unit(2, 50, confidence=2, order=1)),
    )
    assert first_order(result.blocks) == [2, 1]


def test_equal_mastery_falls_back_to_course_order() -> None:
    free = tuple(Interval(at(d, 18), at(d, 18, 50)) for d in range(1, 8))
    _, result = make(
        free=free,
        assessments=(exam(1, at(8, 9), 1, 2),),
        # Unit 2 has the lower id but comes later in the course.
        topics=(unit(1, 50, mastery=0.4, order=0), unit(2, 50, mastery=0.4, order=3)),
    )
    assert first_order(result.blocks) == [1, 2]


# --- reasons -------------------------------------------------------------------------------


def reasons(result_blocks: tuple[Block, ...], n: int) -> list[str]:
    return [b.reason for b in result_blocks if b.topic_id == UUID(int=n)]


def test_low_mastery_takes_low_confidences_place() -> None:
    _, result = make(
        free=evenings(14),
        assessments=(exam(1, at(14, 9), 1, 2, 3),),
        topics=(
            unit(1, 100, mastery=0.3, confidence=5),  # weak by mastery, though rated 5
            unit(2, 100, mastery=0.6, confidence=1),  # rated 1, but mastery says otherwise
            unit(3, 100, confidence=1),  # no mastery: the rating decides, as before
        ),
    )
    assert reasons(result.blocks, 1)[0] == "low_mastery"
    assert reasons(result.blocks, 2)[0] == "workload"
    assert reasons(result.blocks, 3)[0] == "low_confidence"
    assert "low_confidence" not in reasons(result.blocks, 2)
    # The second day is still the spacing block.
    assert reasons(result.blocks, 1)[1] == "spacing"


def test_mastery_of_exactly_a_half_is_not_low() -> None:
    _, result = make(
        free=evenings(14),
        assessments=(exam(1, at(14, 9), 1),),
        topics=(unit(1, 100, mastery=0.5),),
    )
    assert "low_mastery" not in reasons(result.blocks, 1)


# --- the scenario: the plan shifts toward weak topics ---------------------------------------


def test_the_plan_shifts_toward_weak_topics() -> None:
    """Two units with equal workload in one assessment, mastery 0.3 and 0.9: the weak one
    gets at least 50 % more planned minutes, and its first block comes first."""
    weak, strong = UUID(int=1), UUID(int=2)
    request = PlanInput(
        NOW,
        evenings(14),
        180,
        UTC_ZONE,
        (exam(1, at(14, 9), 1, 2),),
        (
            TopicInput(weak, topic(1).module_id, 300, None, order=1, mastery=0.3),
            TopicInput(strong, topic(2).module_id, 300, None, order=0, mastery=0.9),
        ),
    )
    result = plan(request)
    check_plan(request, result)
    minutes = {u: sum(b.minutes for b in result.blocks if b.topic_id == u) for u in (weak, strong)}
    print(f"\nweak (0.3): {minutes[weak]} min · strong (0.9): {minutes[strong]} min")
    assert minutes[weak] >= 1.5 * minutes[strong]
    # Needed: 120 % and 70 % of 300 (360 and 210); planned in 50-minute blocks.
    assert [required_minutes(t, 0) for t in request.topics] == [360, 210]
    assert (minutes[weak], minutes[strong]) == (400, 250)
    first = {u: min(b.start for b in result.blocks if b.topic_id == u) for u in (weak, strong)}
    assert first[weak] < first[strong]

    # The same plan with mastery ignored: equal time, course order first.
    plain = replace(request, topics=tuple(replace(t, mastery=None) for t in request.topics))
    flat = plan(plain)
    same = {u: sum(b.minutes for b in flat.blocks if b.topic_id == u) for u in (weak, strong)}
    assert same[weak] == same[strong] == 300
    assert first_order(flat.blocks) == [2, 1]


# --- text ----------------------------------------------------------------------------------


def block(reason: str) -> Block:
    return Block(
        BLOCK_START,
        BLOCK_START + timedelta(minutes=50),
        MODULE,
        TEST,
        TOPIC,
        "study",
        reason,  # type: ignore[arg-type]
    )


def test_the_low_mastery_text() -> None:
    weak = replace(ESTIMATED, mastery=0.344, mastery_attempts=9)
    assert explain.reason_text(block("low_mastery"), facts(weak)) == (
        "Your mastery is ≈ 34 % (estimated from 9 answers), so it gets 16 % more time. "
        "≈ 40 min estimated from 13 slides; 15 min studied so far (measured, 1 session)."
    )


def test_a_strong_units_workload_sentence_says_why_it_gets_less_time() -> None:
    strong = replace(ESTIMATED, mastery=0.86, mastery_attempts=12)
    assert explain.reason_text(block("workload"), facts(strong)) == (
        "≈ 40 min estimated from 13 slides; 15 min studied so far (measured, 1 session); "
        "mastery ≈ 86 % (estimated from 12 answers), so 30 % less time."
    )
    # 0.5 or a weak unit: nothing about less time.
    for value in (0.5, 0.3):
        middling = replace(ESTIMATED, mastery=value, mastery_attempts=3)
        assert "less time" not in explain.reason_text(block("workload"), facts(middling))


def test_mastery_text_never_predicts_an_exam() -> None:
    for value in (0.1, 0.9):
        found = replace(ESTIMATED, mastery=value, mastery_attempts=4)
        for reason in ("low_mastery", "workload", "urgency"):
            text = explain.reason_text(block(reason), facts(found)).lower()
            for word in ("predict", "mark", "score", "pass", "grade"):
                assert word not in text


def test_the_basis_mentions_mastery_and_the_practice_trigger_summary() -> None:
    assert "mastery" in explain.BASIS and "confidence" in explain.BASIS
    assert explain.version_summary("practice", timezone=UTC_ZONE) == (
        "Your practice changed how strong some topics are."
    )


# --- methods -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("first", "confidence", "mastery", "method"),
    [
        (True, 5, 0.3, "first_pass"),  # mastery below 0.5 wins over a 5
        (True, 1, 0.5, "active_recall"),  # 0.5 or more wins over a 1
        (True, None, 0.9, "active_recall"),
        (True, 2, None, "first_pass"),  # no mastery: the confidence rule
        (True, 4, None, "active_recall"),
        (False, 1, 0.1, "practice"),  # later blocks whatever the mastery
    ],
)
def test_the_first_block_method_follows_mastery(
    first: bool, confidence: int | None, mastery: float | None, method: str
) -> None:
    assert choose(BlockFacts("study", first, confidence, mastery)).method == method


def test_block_facts_carry_mastery() -> None:
    start = datetime(2026, 11, 23, 16, 0, tzinfo=UTC)
    blocks = [
        Block(start, start + timedelta(minutes=50), MODULE, TEST, TOPIC, "study", "low_mastery"),
        Block(
            start + timedelta(hours=1),
            start + timedelta(hours=1, minutes=50),
            MODULE,
            TEST,
            TOPIC,
            "study",
            "workload",
        ),
    ]
    found = block_facts(blocks, lambda _: 5, lambda _: 0.2)
    assert [(f.first_for_topic, f.mastery) for f in found] == [(True, 0.2), (False, 0.2)]
    assert [choose(f).method for f in found] == ["first_pass", "practice"]
    # Without a mastery callable, as before.
    assert block_facts(blocks, lambda _: 5)[0].mastery is None
