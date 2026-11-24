"""Topic mastery v1 (ADR 0027): Hypothesis properties, then examples (the README's worked
examples, the sentences, bands, local days and the rating). Pure: no database."""

import itertools
import random
import uuid
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app.services.mastery.constants import (
    HALF_LIFE_DAYS,
    MIN_ATTEMPTS,
    PRIOR_ATTEMPTS,
    RECALL_AHEAD_DAYS,
)
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
def items(
    draw: st.DrawFn,
    max_items: int = 4,
    *,
    min_items: int = 0,
    start: datetime = BASE,
    max_gap: int = 60 * 24 * 20,
    min_reviews: int = 0,
) -> list[ItemLog]:
    """Up to ``max_items`` items, each reviewed up to 5 times from ``start``, ``max_gap``
    minutes apart at most."""
    out = []
    for _ in range(draw(st.integers(min_items, max_items))):
        gaps = draw(st.lists(st.integers(1, max_gap), min_size=min_reviews, max_size=5))
        grades = draw(st.lists(st.integers(1, 4), min_size=len(gaps), max_size=len(gaps)))
        times = [start + timedelta(minutes=sum(gaps[: i + 1])) for i in range(len(gaps))]
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


def with_review(found: list[ItemLog], target: int, at: datetime, grade: int) -> list[ItemLog]:
    """``found`` with one more review: of item ``target``, or of a new item when ``target``
    is past the end."""
    if target >= len(found):
        return [*found, logged(uuid.UUID(int=0), [(at, grade)])]
    item = found[target]
    plan = [(r.at, r.grade) for r in item.reviews] + [(at, grade)]
    return [logged(item.item_id, plan, item.active) if i is item else i for i in found]


@settings(max_examples=300, deadline=None)
@given(items(), quiz_answers, priors, st.integers(0, 4))
def test_a_new_review_ranks_again_hard_good_easy(
    found: list[ItemLog], quiz: list[QuizAnswer], prior: Prior, target: int
) -> None:
    """One more review of one item at a fixed time: a better grade never gives less."""
    values = [run(with_review(found, target, AT, g), quiz, prior).value for g in (1, 2, 3, 4)]
    for worse, better in itertools.pairwise(values):
        assert worse <= better + 1e-12, values


# Items reviewed in the 40 days before AT, at least once (five gaps of at most 8 days).
recent_items = items(
    min_items=1, max_items=3, start=AT - timedelta(days=40), max_gap=60 * 24 * 8, min_reviews=1
)


def recall_in_a_week(item: ItemLog, at: datetime) -> float | None:
    return summarise_item(item, at, ZoneInfo(UTC_NAME)).recall


@settings(max_examples=300, deadline=None)
@given(items(), recent_items, quiz_answers, priors, st.integers(0, 2))
def test_a_new_again_never_raises_it_unless_fsrs_raises_that_items_recall(
    old: list[ItemLog],
    recent: list[ItemLog],
    quiz: list[QuizAnswer],
    prior: Prior,
    target: int,
) -> None:
    """An Again on an item already reviewed. FSRS models the exposure itself as building
    memory: an item whose memory had faded below what relearning leaves (untouched for a
    month, or failed and left for weeks) gains recall from an Again, and so can the value.
    Only that case is excluded (README, "Edge cases")."""
    found = old + recent
    index = len(old) + target % len(recent)
    again = with_review(found, index, AT, 1)
    if found[index].active:
        before_r, after_r = recall_in_a_week(found[index], AT), recall_in_a_week(again[index], AT)
        if before_r is not None and after_r is not None and after_r > before_r:
            return  # the exception
    before = run(found, quiz, prior).value
    after = run(again, quiz, prior).value
    assert after <= before + 1e-12, (before, after)


def test_an_again_can_raise_it_when_the_card_had_faded() -> None:
    """The exception, twice: rated 1, one card failed twice in its first minutes, then Again
    again 20 or 100 days on. Relearning leaves it more recall in a week than it had."""
    t = datetime(2026, 9, 1, 14, 55, tzinfo=UTC)
    plan = [(t, 1), (t + timedelta(minutes=4), 1)]
    for days, values in ((20, (0.062, 0.074)), (100, (0.050, 0.075))):
        at = t + timedelta(days=days)
        card = logged(uuid.uuid4(), plan)
        before = run([card], [], Prior(1, "session"), at)
        after = run(with_review([card], 0, at, 1), [], Prior(1, "session"), at)
        assert (round(before.value, 3), round(after.value, 3)) == values
        assert after.components.recall is not None and before.components.recall is not None
        assert after.components.recall > before.components.recall


@settings(max_examples=300, deadline=None)
@given(items(), quiz_answers, priors)
def test_without_enough_attempts_there_is_no_band(
    found: list[ItemLog], quiz: list[QuizAnswer], prior: Prior
) -> None:
    result = run(found, quiz, prior)
    if result.status == "not_enough":
        assert result.band is None
    else:
        assert result.band == band(result.value)


# --- Examples: the README's worked examples -------------------------------------------


EVENING = datetime(2026, 11, 2, 18, 0, tzinfo=UTC)


def ten_good_cards() -> list[ItemLog]:
    """Ten cards answered Good on Monday evening and Good again on Tuesday."""
    return [
        logged(
            uuid.uuid4(),
            [(EVENING + timedelta(minutes=k), 3), (EVENING + timedelta(days=1, minutes=k), 3)],
        )
        for k in range(10)
    ]


def test_worked_example_a_new_topic_rated_2() -> None:
    result = run([], [], Prior(2, "starting"), EVENING)
    assert (result.value, result.band, result.status) == (0.25, None, "not_enough")
    assert result.basis == (
        "Not enough practice yet: 0 of 3 attempts. Your starting rating of 2 of 5 is used for now."
    )


def test_worked_example_ten_cards_good_twice() -> None:
    """Rated 3 in the session; read on Wednesday at 20:00. Recall is R a week later."""
    result = run(ten_good_cards(), [], Prior(3, "session"), EVENING + timedelta(days=2, hours=2))
    c = result.components
    assert (c.accuracy, c.prior, c.weight, c.recall_weight) == (1.0, 0.5, 20 / 23, 10 / 13)
    assert c.recall is not None and round(c.recall, 4) == 0.8937
    assert round(result.value, 4) == 0.9158
    assert (result.status, result.band) == ("estimated", "strong")
    assert result.basis == (
        "≈ 92 % (estimated) from recall in a week ≈ 89 % across 10 practised items, 20 of 20 "
        "recent answers right, and your latest session rating of 3 of 5."
    )


def test_worked_example_a_topic_untouched_for_30_days() -> None:
    """The same, 30 days after Tuesday's reviews: recall decays, accuracy and the weights
    don't move."""
    result = run(ten_good_cards(), [], Prior(3, "session"), EVENING + timedelta(days=31, hours=2))
    c = result.components
    assert (c.accuracy, c.weight, c.recall_weight) == (1.0, 20 / 23, 10 / 13)
    assert c.recall is not None and round(c.recall, 4) == 0.7594
    assert round(result.value, 4) == 0.8538
    assert (result.status, result.band) == ("estimated", "strong")
    assert result.basis.startswith("≈ 85 % (estimated) from recall in a week ≈ 76 % across 10 ")


def test_three_agains_read_as_weak_and_a_fourth_lowers_it() -> None:
    """The review of #50: four new cards, no rating, each answered Again. Recall straight
    after read 100 % and a fourth Again raised the value; a week ahead, it lowers it."""
    cards = [logged(uuid.uuid4(), [(EVENING + timedelta(minutes=k), 1)]) for k in range(4)]
    at = EVENING + timedelta(minutes=10)
    three = run(cards[:3], [], Prior(None, "none"), at)
    four = run(cards, [], Prior(None, "none"), at)
    assert (round(three.value, 4), round(four.value, 4)) == (0.3497, 0.3404)
    assert three.band == "weak"
    assert three.basis == (
        "≈ 35 % (estimated) from recall in a week ≈ 58 % across 3 practised items, 0 of 3 "
        "recent answers right, and no rating yet (50 % assumed)."
    )


def test_recall_in_a_week_after_one_review_of_a_new_card() -> None:
    """The figures ADR 0028 quotes (fsrs 6.3.3, default parameters, retention 0.9)."""
    found = []
    for grade in (1, 2, 3, 4):
        item = logged(uuid.uuid4(), [(EVENING, grade)])
        found.append(round(summarise_item(item, EVENING, ZoneInfo("UTC")).recall or 0, 2))
    assert found == [0.58, 0.75, 0.81, 0.91]


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
    assert (MIN_ATTEMPTS, PRIOR_ATTEMPTS, RECALL_AHEAD_DAYS) == (3, 3, 7)


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
