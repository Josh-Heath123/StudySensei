"""Topic mastery v1 (ADR 0027): Hypothesis properties, then examples (the README's worked
examples, the sentences, bands, local days and the rating). Pure: no database."""

import random
import uuid
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app.services.mastery.constants import HALF_LIFE_DAYS, MIN_ATTEMPTS, PRIOR_ATTEMPTS
from app.services.mastery.formula import (
    Attempt,
    ItemLog,
    Mastery,
    Prior,
    QuizAnswer,
    ReviewLog,
    accuracy,
    band,
    mastery,
    resolve_prior,
    summarise_item,
    topic_mastery,
)
from app.services.planning.subtree import make_tree
from app.services.practice.scheduling import MemoryState, SchedulingSettings, schedule

BASE = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
# Every generated event falls before this.
AT = BASE + timedelta(days=101)
DEFAULT = SchedulingSettings()
UTC_NAME = "UTC"

priors = st.one_of(
    st.just(Prior(None, "none")),
    st.builds(Prior, st.integers(1, 5), st.sampled_from(["session", "starting", "subtopics"])),
)


def logged(item_id: uuid.UUID, plan: list[tuple[datetime, int]], active: bool = True) -> ItemLog:
    """An item reviewed at those times with those grades, its states from FSRS."""
    state: MemoryState | None = None
    reviews = []
    for at, grade in sorted(plan):
        state, _ = schedule(state, grade, at, DEFAULT)
        reviews.append(ReviewLog(at, grade, state))
    return ItemLog(item_id, active, tuple(reviews))


@st.composite
def items(draw: st.DrawFn, max_items: int = 4) -> list[ItemLog]:
    out = []
    for _ in range(draw(st.integers(0, max_items))):
        gaps = draw(st.lists(st.integers(1, 60 * 24 * 20), max_size=5))
        grades = draw(st.lists(st.integers(1, 4), min_size=len(gaps), max_size=len(gaps)))
        times = [BASE + timedelta(minutes=sum(gaps[: i + 1])) for i in range(len(gaps))]
        active = draw(st.sampled_from([True, True, True, False]))
        out.append(logged(draw(st.uuids()), list(zip(times, grades, strict=True)), active))
    return out


quiz_answers = st.lists(
    st.builds(
        QuizAnswer,
        st.integers(0, 60 * 24 * 100).map(lambda m: BASE + timedelta(minutes=m)),
        st.booleans(),
    ),
    max_size=8,
)


def run(found: list[ItemLog], quiz: list[QuizAnswer], prior: Prior, at: datetime = AT) -> Mastery:
    return mastery(found, quiz, prior, at, UTC_NAME)


# --- Properties -----------------------------------------------------------------------


@settings(max_examples=300, deadline=None)
@given(items(), quiz_answers, priors)
def test_the_value_is_always_between_0_and_1(
    found: list[ItemLog], quiz: list[QuizAnswer], prior: Prior
) -> None:
    result = run(found, quiz, prior)
    assert 0.0 <= result.value <= 1.0
    assert result.band == band(result.value)


@settings(max_examples=300, deadline=None)
@given(items(), quiz_answers, priors, st.booleans())
def test_a_new_right_answer_never_lowers_it_and_a_wrong_one_never_raises_it(
    found: list[ItemLog], quiz: list[QuizAnswer], prior: Prior, correct: bool
) -> None:
    """All else equal: one more answered question, the newest attempt."""
    before = run(found, quiz, prior).value
    after = run(found, [*quiz, QuizAnswer(AT, correct)], prior).value
    if correct:
        assert after >= before - 1e-12
    else:
        assert after <= before + 1e-12


@settings(max_examples=300, deadline=None)
@given(items(), quiz_answers, priors, st.integers(1, 60 * 24 * 400))
def test_with_no_new_attempts_it_never_rises_as_time_passes(
    found: list[ItemLog], quiz: list[QuizAnswer], prior: Prior, minutes: int
) -> None:
    now = run(found, quiz, prior)
    later = run(found, quiz, prior, AT + timedelta(minutes=minutes))
    assert later.value <= now.value
    # A doesn't move and n doesn't change.
    assert later.components.accuracy == now.components.accuracy
    assert later.samples.attempts == now.samples.attempts


@settings(max_examples=300, deadline=None)
@given(priors)
def test_with_no_attempts_it_is_the_prior(prior: Prior) -> None:
    result = run([logged(uuid.uuid4(), [])], [], prior)
    assert result.value == result.components.prior
    assert result.status == "not_enough"


@settings(max_examples=300, deadline=None)
@given(items(), quiz_answers, st.integers(0, 40))
def test_the_more_attempts_the_less_a_rating_change_moves_it(
    found: list[ItemLog], quiz: list[QuizAnswer], extra: int
) -> None:
    def swing(more: int) -> float:
        answers = quiz + [QuizAnswer(AT, k % 2 == 0) for k in range(more)]
        high = run(found, answers, Prior(5, "session")).value
        low = run(found, answers, Prior(1, "session")).value
        return high - low

    base = run(found, quiz, Prior(3, "session")).samples.attempts
    assert swing(extra + 1) <= swing(extra) + 1e-12
    if base + extra >= 30:
        assert swing(extra) < 0.10


def test_at_30_attempts_a_full_rating_change_moves_it_under_a_tenth() -> None:
    quiz = [QuizAnswer(BASE + timedelta(days=k), k % 3 != 0) for k in range(30)]
    high = run([], quiz, Prior(5, "session")).value
    low = run([], quiz, Prior(1, "session")).value
    assert 0 < high - low < 0.10


@settings(max_examples=300, deadline=None)
@given(items(), quiz_answers, priors)
def test_an_item_in_both_a_chapter_and_its_subtopic_counts_once(
    found: list[ItemLog], quiz: list[QuizAnswer], prior: Prior
) -> None:
    assert run(found + found, quiz, prior) == run(found, quiz, prior)


@settings(max_examples=300, deadline=None)
@given(items(max_items=3), priors, st.integers(1, 4), st.integers(1, 120))
def test_same_day_repeats_add_no_attempts(
    found: list[ItemLog], prior: Prior, grade: int, minutes: int
) -> None:
    reviewed = [i for i in found if i.reviews]
    assume(reviewed)
    target = reviewed[0]
    last = max(r.at for r in target.reviews)
    repeat_at = last + timedelta(minutes=minutes)
    assume(repeat_at.date() == last.date())
    plan = [(r.at, r.grade) for r in target.reviews] + [(repeat_at, grade)]
    again = [logged(target.item_id, plan, target.active) if i is target else i for i in found]
    before, after = run(found, [], prior), run(again, [], prior)
    assert after.samples.attempts == before.samples.attempts
    assert after.samples.reviews == before.samples.reviews + 1


@settings(max_examples=300, deadline=None)
@given(quiz_answers.filter(bool), priors)
def test_a_quiz_only_topic_uses_accuracy_alone(quiz: list[QuizAnswer], prior: Prior) -> None:
    result = run([], quiz, prior)
    c = result.components
    assert c.recall is None and c.accuracy is not None
    assert abs(result.value - (c.weight * c.accuracy + (1 - c.weight) * c.prior)) < 1e-12


@settings(max_examples=300, deadline=None)
@given(items(), quiz_answers, priors, st.randoms(use_true_random=False))
def test_the_order_of_the_inputs_never_matters(
    found: list[ItemLog], quiz: list[QuizAnswer], prior: Prior, rng: random.Random
) -> None:
    shuffled = [replace(i, reviews=tuple(rng.sample(i.reviews, len(i.reviews)))) for i in found]
    rng.shuffle(shuffled)
    assert run(shuffled, rng.sample(quiz, len(quiz)), prior) == run(found, quiz, prior)


# --- Examples: the README's worked examples -------------------------------------------


EVENING = datetime(2026, 11, 2, 18, 0, tzinfo=UTC)


def ten_good_cards() -> list[ItemLog]:
    return [logged(uuid.uuid4(), [(EVENING + timedelta(minutes=k), 3)]) for k in range(10)]


def test_worked_example_a_new_topic_rated_2() -> None:
    result = run([], [], Prior(2, "starting"), EVENING)
    assert (result.value, result.band, result.status) == (0.25, "weak", "not_enough")
    assert result.basis == (
        "Not enough practice yet: 0 of 3 attempts. Your starting rating of 2 of 5 is used for now."
    )


def test_worked_example_ten_good_reviews() -> None:
    """Ten cards answered Good on Monday evening, rated 3 in the session, seen on Tuesday at
    20:00 (FSRS counts whole days since a review: one each)."""
    result = run(ten_good_cards(), [], Prior(3, "session"), EVENING + timedelta(days=1, hours=2))
    c = result.components
    assert (c.accuracy, c.prior, c.weight, c.recall_weight) == (1.0, 0.5, 10 / 13, 10 / 13)
    assert c.recall is not None and round(c.recall, 4) == 0.9468
    assert round(result.value, 4) == 0.9133
    assert (result.status, result.band) == ("estimated", "strong")
    assert result.basis == (
        "≈ 91 % (estimated) from recall of ≈ 95 % across 10 practised items, 10 of 10 recent "
        "answers right, and your latest session rating of 3 of 5."
    )


def test_worked_example_a_topic_untouched_for_30_days() -> None:
    """The same, 30 days on: recall decays, accuracy and the weights don't move."""
    result = run(ten_good_cards(), [], Prior(3, "session"), EVENING + timedelta(days=31, hours=2))
    c = result.components
    assert (c.accuracy, c.weight, c.recall_weight) == (1.0, 10 / 13, 10 / 13)
    assert c.recall is not None and round(c.recall, 4) == 0.6644
    assert round(result.value, 4) == 0.7830
    assert (result.status, result.band) == ("estimated", "developing")
    assert result.basis.startswith("≈ 78 % (estimated) from recall of ≈ 66 % across 10 ")


# --- Examples: details ----------------------------------------------------------------


def test_attempts_are_first_reviews_of_a_local_day() -> None:
    """In Johannesburg (UTC+2), 21:30 and 22:30 UTC on one date are two local days."""
    item = logged(
        uuid.uuid4(),
        [
            (datetime(2026, 11, 2, 21, 30, tzinfo=UTC), 1),
            (datetime(2026, 11, 2, 21, 31, tzinfo=UTC), 3),  # a learning step: no attempt
            (datetime(2026, 11, 2, 22, 30, tzinfo=UTC), 2),  # 00:30 on the 3rd locally
        ],
    )
    at = datetime(2026, 11, 4, tzinfo=UTC)
    summary = summarise_item(item, at, ZoneInfo("Africa/Johannesburg"))
    assert [(a.day, a.score) for a in summary.attempts] == [
        (date(2026, 11, 2), 0.0),
        (date(2026, 11, 3), 0.5),
    ]
    assert summary.reviews == 3
    assert len(summarise_item(item, at, ZoneInfo("UTC")).attempts) == 1


def test_recency_weighting_halves_every_30_days() -> None:
    newest = datetime(2026, 11, 2, tzinfo=UTC)
    old = Attempt(newest - timedelta(days=HALF_LIFE_DAYS), date(2026, 10, 3), 0.0, "quiz")
    new = Attempt(newest, date(2026, 11, 2), 1.0, "quiz")
    assert accuracy([old, new]) == 1 / 1.5


def test_a_suspended_item_counts_its_attempts_but_not_its_recall() -> None:
    item = logged(uuid.uuid4(), [(EVENING, 3)], active=False)
    result = run([item], [], Prior(None, "none"), EVENING + timedelta(hours=1))
    assert result.components.recall is None
    assert (result.samples.items_active, result.samples.attempts) == (0, 1)


def test_sentences_label_every_number() -> None:
    quiz = [QuizAnswer(EVENING + timedelta(minutes=k), k != 0) for k in range(4)]
    hard = logged(uuid.uuid4(), [(EVENING, 2)])
    result = run([hard], quiz, Prior(None, "none"), EVENING + timedelta(hours=1))
    assert result.status == "estimated"
    assert result.basis.endswith(
        "across 1 practised item, 3 of 5 recent answers right (1 hard), and no rating yet "
        "(50 % assumed)."
    )
    few = run([], quiz[:2], Prior(None, "none"), EVENING + timedelta(hours=1))
    assert few.basis == (
        "Not enough practice yet: 2 of 3 attempts. With no rating yet, 50 % is assumed for now."
    )
    quiz_only = run([], quiz, Prior(4, "subtopics"), EVENING + timedelta(hours=1))
    assert " from 3 of 4 recent answers right and your subtopics' mean rating of 4 of 5." in (
        quiz_only.basis
    )


def test_bands_and_the_minimum() -> None:
    assert [band(v) for v in (0.0, 0.4999, 0.5, 0.7999, 0.8, 1.0)] == [
        "weak",
        "weak",
        "developing",
        "developing",
        "strong",
        "strong",
    ]
    assert (MIN_ATTEMPTS, PRIOR_ATTEMPTS) == (3, 3)


def test_events_after_at_are_ignored() -> None:
    item = logged(uuid.uuid4(), [(EVENING, 3), (EVENING + timedelta(days=5), 1)])
    quiz = [QuizAnswer(EVENING + timedelta(days=5), False)]
    early = run([item], quiz, Prior(3, "starting"), EVENING + timedelta(days=1))
    assert (early.samples.reviews, early.samples.attempts, early.samples.quiz_answers) == (1, 1, 0)


def test_topic_mastery_takes_summaries() -> None:
    summary = summarise_item(logged(uuid.uuid4(), [(EVENING, 4)]), EVENING, ZoneInfo("UTC"))
    assert topic_mastery([summary], [], Prior(3, "starting"), EVENING).samples.attempts == 1


def test_the_prior_prefers_a_session_rating_then_the_starting_one_then_the_subtopics() -> None:
    chapter, sub_a, sub_b, leaf = (uuid.UUID(int=k) for k in range(1, 5))
    tree = make_tree([(chapter, None), (sub_a, chapter), (sub_b, chapter), (leaf, sub_b)])
    assert resolve_prior(tree, chapter, {chapter: 4}, {chapter: 2}) == Prior(4, "session")
    assert resolve_prior(tree, chapter, {}, {chapter: 2}) == Prior(2, "starting")
    # Unrated chapter: its subtopics' ratings, a session rating beating a starting one:
    # sub_a 2 (session, over its starting 5), leaf 5 (starting): mean 3.5 → 4.
    assert resolve_prior(tree, chapter, {sub_a: 2}, {sub_a: 5, leaf: 5}) == Prior(4, "subtopics")
    assert resolve_prior(tree, chapter, {}, {}) == Prior(None, "none")
    assert resolve_prior(tree, leaf, {}, {chapter: 5}) == Prior(None, "none")
