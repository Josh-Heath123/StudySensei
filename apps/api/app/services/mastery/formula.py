"""Topic mastery v1 (ADR 0027). Pure: no database, no clock, no AI.

Mastery is an estimate of how well the student knows a topic now, from their own practice and
ratings. It is never an exam prediction. ``README.md`` beside this file explains every input,
the constants (``constants.py``) and worked examples.

For a topic's subtree (decision 0019: a topic covers its subtree, each item counted once), as of
a time ``at``:

- **Recall M:** the mean FSRS retrievability one week after ``at`` (recall in a week, ADR 0028)
  over the subtree's active items that have a state (``scheduling.retrievability``, the one FSRS
  call site). None if none was reviewed. R at ``at`` itself would be 1.0 for a day after any
  review, even an Again, since py-fsrs counts whole days.
- **Accuracy A:** attempts are the first review of each item on each local day (Again 0,
  Hard 0.5, Good 1, Easy 1) and each answered Quiz me question (right 1, wrong 0). Later reviews
  of an item the same day are learning-step repeats, not attempts. A is the mean weighted by
  0.5^(age / 30 days), the age measured from the newest attempt, so A stays put while no new
  attempts arrive. ``n`` is the number of attempts.
- **Prior P:** the rating (``Prior``) mapped (c - 1) / 4; 0.5 when unrated.
- **Value:** ``0.6·g·M + (1 - 0.6·g)·(w·A + (1 - w)·P)`` with ``w = n / (n + 3)`` and
  ``g = m / (m + 3)``, m the items reviewed (``_value`` says why).
- **Status:** "not_enough" below 3 attempts, else "estimated".
- **Band:** weak < 0.5 <= developing < 0.8 <= strong; none while "not_enough".

The result doesn't depend on the order of its inputs: items are de-duplicated by id and every
sum is ``math.fsum``.
"""

import math
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from app.services.mastery.constants import (
    DEVELOPING_FROM,
    GRADE_SCORES,
    HALF_LIFE_DAYS,
    MIN_ATTEMPTS,
    PRIOR_ATTEMPTS,
    RATING_MAX,
    RATING_MIN,
    RECALL_AHEAD_DAYS,
    RECALL_SHARE,
    STRONG_FROM,
    UNRATED_PRIOR,
)
from app.services.planning.subtree import Tree, descendants, subtree_confidence
from app.services.practice.scheduling import MemoryState, retrievability

Status = Literal["not_enough", "estimated"]
Band = Literal["weak", "developing", "strong"]
RatingSource = Literal["session", "starting", "subtopics", "none"]
AttemptSource = Literal["review", "quiz"]

_DAY_SECONDS = 86_400


# --- Inputs ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReviewLog:
    """One review of an item: when, the grade, and the FSRS state it led to (None for reviews
    from before scheduling)."""

    at: datetime
    grade: int
    state_after: MemoryState | None


@dataclass(frozen=True)
class ItemLog:
    """A practice item in the subtree (never a rejected one) and its reviews, in any order."""

    item_id: uuid.UUID
    active: bool
    reviews: tuple[ReviewLog, ...]


@dataclass(frozen=True)
class QuizAnswer:
    """One answered Quiz me question, graded by code (``tutor.grading.grade``)."""

    at: datetime
    correct: bool


@dataclass(frozen=True)
class Prior:
    """The rating the prior comes from: 1 to 5, or None (unrated)."""

    confidence: int | None
    source: RatingSource


@dataclass(frozen=True)
class Attempt:
    at: datetime
    # The local day (users.timezone) it happened on.
    day: date
    score: float
    source: AttemptSource


@dataclass(frozen=True)
class ItemSummary:
    """One item as of ``at``: its recall (None when not active or never scheduled), its
    attempts and how many reviews it has."""

    item_id: uuid.UUID
    active: bool
    recall: float | None
    attempts: tuple[Attempt, ...]
    reviews: int


# --- Output ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Components:
    recall: float | None  # M: recall in a week
    accuracy: float | None  # A
    prior: float  # P
    weight: float  # w = n / (n + k): the attempts' weight against the prior
    recall_weight: float  # g = m / (m + k), m the items reviewed: scales recall's share


@dataclass(frozen=True)
class Samples:
    # Active items with a state (M's sample) and active items in all.
    items_reviewed: int
    items_active: int
    # n: review attempts plus quiz answers.
    attempts: int
    quiz_answers: int
    # Every review up to ``at``, same-day repeats included.
    reviews: int
    # From the first attempt's local day to the last's, inclusive (0 with no attempts).
    days_spanned: int
    rating_source: RatingSource


@dataclass(frozen=True)
class Mastery:
    value: float
    status: Status
    # None while status is "not_enough".
    band: Band | None
    components: Components
    samples: Samples
    # One sentence, every number labelled.
    basis: str


@dataclass(frozen=True)
class Weights:
    value: float
    weight: float
    recall_weight: float


# --- Per item -------------------------------------------------------------------------


def _local_day(at: datetime, tz: ZoneInfo) -> date:
    return at.astimezone(tz).date()


def summarise_item(item: ItemLog, at: datetime, tz: ZoneInfo) -> ItemSummary:
    """The item as of ``at``: reviews after it are ignored. Its recall is FSRS's R a week
    after ``at``."""
    reviews = sorted((r for r in item.reviews if r.at <= at), key=lambda r: (r.at, r.grade))
    attempts: list[Attempt] = []
    days: set[date] = set()
    state: MemoryState | None = None
    for review in reviews:
        day = _local_day(review.at, tz)
        if day not in days:  # the day's first review; later ones are learning-step repeats
            days.add(day)
            attempts.append(Attempt(review.at, day, GRADE_SCORES[review.grade], "review"))
        if review.state_after is not None:
            state = review.state_after
    ahead = at + timedelta(days=RECALL_AHEAD_DAYS)
    recall = retrievability(state, ahead) if item.active and state is not None else None
    return ItemSummary(item.item_id, item.active, recall, tuple(attempts), len(reviews))


def quiz_attempt(answer: QuizAnswer, tz: ZoneInfo) -> Attempt:
    return Attempt(answer.at, _local_day(answer.at, tz), 1.0 if answer.correct else 0.0, "quiz")


# --- The topic ------------------------------------------------------------------------


def resolve_prior(
    tree: Tree,
    topic_id: uuid.UUID,
    latest_session: Mapping[uuid.UUID, int],
    starting: Mapping[uuid.UUID, int | None],
) -> Prior:
    """The topic's latest session reflection rating, else its starting confidence; for a topic
    rated neither way, the mean of its rated descendants (each rated the same way), rounded
    half up as ``subtree_confidence`` does for the planner; else unrated."""
    if (found := latest_session.get(topic_id)) is not None:
        return Prior(found, "session")
    if (found := starting.get(topic_id)) is not None:
        return Prior(found, "starting")
    effective: dict[uuid.UUID, int | None] = {
        t: latest_session.get(t, starting.get(t)) for t in descendants(tree, topic_id)
    }
    value, source = subtree_confidence(tree, topic_id, effective)
    return Prior(value, "subtopics") if source == "subtopics" else Prior(None, "none")


def prior_value(prior: Prior) -> float:
    if prior.confidence is None:
        return UNRATED_PRIOR
    return (prior.confidence - RATING_MIN) / (RATING_MAX - RATING_MIN)


def accuracy(attempts: Iterable[Attempt]) -> float | None:
    """The recency-weighted mean score. Ages are measured from the newest attempt, so the
    result depends only on the attempts, never on when it is computed."""
    found = list(attempts)
    if not found:
        return None
    newest = max(a.at for a in found)
    weights = [
        0.5 ** ((newest - a.at).total_seconds() / _DAY_SECONDS / HALF_LIFE_DAYS) for a in found
    ]
    return math.fsum(w * a.score for w, a in zip(weights, found, strict=True)) / math.fsum(weights)


def band(value: float) -> Band:
    if value < DEVELOPING_FROM:
        return "weak"
    return "developing" if value < STRONG_FROM else "strong"


def _value(recall: float | None, acc: float | None, prior: float, n: int, m: int) -> Weights:
    """The value, as ADR 0027 states it:

    - accuracy is shrunk to the prior by the attempts: ``A' = w·A + (1 - w)·P``,
      ``w = n / (n + k)``;
    - recall carries its share 0.6 scaled by its own sample, the items reviewed:
      ``g = m / (m + k)``;
    - ``value = 0.6·g·M + (1 - 0.6·g)·A'``, which tends to ``E = 0.6·M + 0.4·A`` as both
      samples grow. With no recall it is ``A'`` (A alone); with no attempts it is ``P``.

    The first draft (``w·E + (1 - w)·P``) failed the monotonicity property: a quiz answer
    raised ``w`` and so the weight on M, which an answer can't move, and a wrong answer could
    raise the value (ADR 0027).
    """
    weight = n / (n + PRIOR_ATTEMPTS)
    recall_weight = m / (m + PRIOR_ATTEMPTS) if recall is not None else 0.0
    if n == 0 or acc is None:
        return Weights(prior, weight, recall_weight)
    shrunk = weight * acc + (1 - weight) * prior
    if recall is None:
        return Weights(shrunk, weight, recall_weight)
    share = RECALL_SHARE * recall_weight
    return Weights(share * recall + (1 - share) * shrunk, weight, recall_weight)


def topic_mastery(
    items: Iterable[ItemSummary], quiz: Iterable[Attempt], prior: Prior, at: datetime
) -> Mastery:
    """Mastery of a subtree from its items (each counted once, by id) and quiz attempts."""
    unique: dict[uuid.UUID, ItemSummary] = {}
    for item in sorted(items, key=lambda i: i.item_id):
        unique.setdefault(item.item_id, item)
    recalls = [i.recall for i in unique.values() if i.recall is not None]
    quiz_found = [a for a in quiz if a.at <= at]
    attempts = [a for i in unique.values() for a in i.attempts] + quiz_found
    n = len(attempts)
    m = math.fsum(recalls) / len(recalls) if recalls else None
    a = accuracy(attempts)
    p = prior_value(prior)
    found = _value(m, a, p, n, len(recalls))
    value = min(1.0, max(0.0, found.value))
    days = [x.day for x in attempts]
    samples = Samples(
        items_reviewed=len(recalls),
        items_active=sum(1 for i in unique.values() if i.active),
        attempts=n,
        quiz_answers=len(quiz_found),
        reviews=sum(i.reviews for i in unique.values()),
        days_spanned=(max(days) - min(days)).days + 1 if days else 0,
        rating_source=prior.source,
    )
    status: Status = "not_enough" if n < MIN_ATTEMPTS else "estimated"
    right = sum(1 for x in attempts if x.score == 1.0)
    hard = sum(1 for x in attempts if 0.0 < x.score < 1.0)
    return Mastery(
        value=value,
        status=status,
        band=None if status == "not_enough" else band(value),
        components=Components(m, a, p, found.weight, found.recall_weight),
        samples=samples,
        basis=basis(value, status, m, samples, right, hard, prior),
    )


def mastery(
    items: Iterable[ItemLog],
    quiz: Iterable[QuizAnswer],
    prior: Prior,
    at: datetime,
    timezone: str,
) -> Mastery:
    """``topic_mastery`` straight from the logs (the loader summarises each item once and
    shares it between the topics whose subtrees hold it)."""
    tz = ZoneInfo(timezone)
    return topic_mastery(
        [summarise_item(i, at, tz) for i in items], [quiz_attempt(q, tz) for q in quiz], prior, at
    )


# --- The sentence ---------------------------------------------------------------------


def percent(value: float) -> str:
    return f"{math.floor(value * 100 + 0.5)} %"


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def _rating(prior: Prior) -> str:
    c = prior.confidence
    return {
        "session": f"your latest session rating of {c} of 5",
        "starting": f"your starting rating of {c} of 5",
        "subtopics": f"your subtopics' mean rating of {c} of 5",
        "none": f"no rating yet ({percent(UNRATED_PRIOR)} assumed)",
    }[prior.source]


def _join(parts: list[str]) -> str:
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + (", and " if len(parts) > 2 else " and ") + parts[-1]


def basis(
    value: float,
    status: Status,
    recall: float | None,
    samples: Samples,
    right: int,
    hard: int,
    prior: Prior,
) -> str:
    """What the value rests on, every number labelled (written by code, never by AI)."""
    if status == "not_enough":
        if prior.source == "none":
            used = f"With no rating yet, {percent(UNRATED_PRIOR)} is assumed for now."
        else:
            rating = _rating(prior)
            used = f"{rating[0].upper()}{rating[1:]} is used for now."
        return f"Not enough practice yet: {samples.attempts} of {MIN_ATTEMPTS} attempts. {used}"
    parts = []
    if recall is not None:
        parts.append(
            f"recall in a week ≈ {percent(recall)} across "
            f"{_plural(samples.items_reviewed, 'practised item')}"
        )
    answers = f"{right} of {_plural(samples.attempts, 'recent answer')} right"
    parts.append(answers + (f" ({hard} hard)" if hard else ""))
    parts.append(_rating(prior))
    return f"≈ {percent(value)} (estimated) from {_join(parts)}."
