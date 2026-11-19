"""Pure metric functions for the evals: no database, no model. Unit-tested in tests/evals/."""

import math
import re
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# A page of a material, by the material's title: ("CH05", 29).
Page = tuple[str, int]


# --- search ---


def first_rank(results: Sequence[Page], acceptable: Collection[Page]) -> int | None:
    """1-based position of the first result on an acceptable page, or None."""
    return next((i for i, page in enumerate(results, start=1) if page in acceptable), None)


def mean_reciprocal_rank(ranks: Sequence[int | None]) -> float:
    """Mean of 1/rank, counting a miss (None) as 0."""
    if not ranks:
        return 0.0
    return sum(1 / rank for rank in ranks if rank) / len(ranks)


def in_top(ranks: Iterable[int | None], k: int) -> int:
    return sum(1 for rank in ranks if rank is not None and rank <= k)


# --- chapters ---


@dataclass(frozen=True)
class ChapterRules:
    """Which chapter a material or a topic belongs to, from the eval config (never app code).

    A material's chapter comes from its title ("CH05", "COS330 Chapter5 Study Notes"); a
    topic's from its top-level ancestor's name ("Ch5 Database and Data Center Security").
    Anything that matches no pattern has no chapter (the study guide, past papers).
    """

    material: tuple[re.Pattern[str], ...]
    topic: re.Pattern[str]

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "ChapterRules":
        return cls(
            tuple(re.compile(pattern) for pattern in config["material_chapter"]),
            re.compile(config["topic_chapter"]),
        )

    def material_chapter(self, title: str) -> int | None:
        for pattern in self.material:
            match = pattern.search(title)
            if match:
                return int(match.group(1))
        return None

    def topic_chapter(self, top_level_name: str) -> int | None:
        match = self.topic.search(top_level_name)
        return int(match.group(1)) if match else None


def top_level_names[K](tree: Mapping[K, tuple[str, K | None]]) -> dict[K, str]:
    """Each topic's root ancestor's name (its own name for a top-level topic).

    ``tree`` maps topic id → (name, parent id).
    """
    roots: dict[K, str] = {}
    for topic in tree:
        current, seen = topic, set()
        while (parent := tree[current][1]) is not None and parent not in seen:
            seen.add(current)
            current = parent
        roots[topic] = tree[current][0]
    return roots


@dataclass
class ChapterCounts:
    same: int = 0
    cross: int = 0
    # The page's material has no chapter (the study guide), or the topic has none.
    unknown: int = 0

    @property
    def total(self) -> int:
        return self.same + self.cross + self.unknown

    def add(self, topic_chapter: int | None, page_chapter: int | None) -> None:
        if topic_chapter is None or page_chapter is None:
            self.unknown += 1
        elif topic_chapter == page_chapter:
            self.same += 1
        else:
            self.cross += 1


# --- topic trees ---


def normalise(name: str) -> str:
    """Case, spacing and dash variants don't make a different topic."""
    dashes = str.maketrans({chr(0x2013): "-", chr(0x2014): "-"})  # en and em dashes
    return " ".join(name.translate(dashes).casefold().split())


@dataclass
class TreeComparison:
    matched: list[tuple[str, str | None]]
    # In the reference but not in the current tree, and the other way round.
    missing: list[tuple[str, str | None]]
    extra: list[tuple[str, str | None]]
    # Same name, different parent: (name, reference parent, current parent).
    moved: list[tuple[str, str | None, str | None]]


def compare_trees(
    reference: Sequence[tuple[str, str | None]], current: Sequence[tuple[str, str | None]]
) -> TreeComparison:
    """Match topics by normalised name. Each is (name, parent name or None)."""
    now = {normalise(name): (name, parent) for name, parent in current}
    then = {normalise(name): (name, parent) for name, parent in reference}
    result = TreeComparison([], [], [], [])
    for key, (name, parent) in then.items():
        if key not in now:
            result.missing.append((name, parent))
            continue
        result.matched.append((name, parent))
        current_parent = now[key][1]
        if normalise(parent or "") != normalise(current_parent or ""):
            result.moved.append((name, parent, current_parent))
    result.extra = [(name, parent) for key, (name, parent) in now.items() if key not in then]
    return result


# --- linking sweep ---


@dataclass(frozen=True)
class ChunkScore:
    """One candidate chunk for a topic: its page and its cosine with the topic."""

    material: str
    page: int
    score: float


@dataclass(frozen=True)
class LinkRule:
    """How similarity links are chosen.

    ``linking.py`` does: the topic's ``cap`` most similar chunks, kept when the score is at
    least ``threshold``. ``delta`` adds the relative rule: also within ``delta`` of the
    topic's best cited-page score (topics without cited pages fall back to the threshold).
    """

    threshold: float
    cap: int
    delta: float | None = None

    @property
    def label(self) -> str:
        rule = f"threshold {self.threshold:.2f}, cap {self.cap}"
        return rule if self.delta is None else f"{rule}, within {self.delta:.2f} of best cited"


def similarity_pages(
    candidates: Sequence[ChunkScore],
    rule: LinkRule,
    *,
    cited: Collection[Page] = (),
    best_cited: float | None = None,
) -> set[Page]:
    """The pages a topic links to by similarity under ``rule``.

    ``candidates`` are the chunks linking may use (already without near-empty pages and the
    student's unlinks). Chunks on cited pages take places in the cap, as in the SQL, but
    their pages are cited links, not similarity ones.
    """
    top = sorted(candidates, key=lambda chunk: chunk.score, reverse=True)[: rule.cap]
    floor = rule.threshold
    if rule.delta is not None and best_cited is not None:
        floor = max(floor, best_cited - rule.delta)
    return {(c.material, c.page) for c in top if c.score >= floor} - set(cited)


# --- tutor ---

# Phrases the tutor uses when the sources don't cover the question (its system prompt asks
# it to say so plainly). A heuristic, reported as such.
_NOT_COVERED = re.compile(
    r"(doesn.t|does not|don.t|do not)\s+(cover|contain|include|say|mention|discuss)"
    r"|not\s+covered|no\s+information\s+(about|on)|isn.t\s+covered",
    re.IGNORECASE,
)


def says_not_covered(text: str, cited: Collection[str]) -> bool:
    """The answer says the material doesn't cover the question, and cites nothing."""
    return not cited and bool(_NOT_COVERED.search(text))


def coverage(
    cited: Collection[Page], sources: Collection[Page], acceptable: Collection[Page]
) -> float | None:
    """Of the acceptable pages that were among the sources, the share the answer cited.

    None when no acceptable page was among the sources (nothing could be cited).
    """
    given = set(sources) & set(acceptable)
    if not given:
        return None
    return len(given & set(cited)) / len(given)


def rate(flags: Sequence[bool]) -> float:
    """The share of True, 0.0 for none."""
    return sum(1 for flag in flags if flag) / len(flags) if flags else 0.0


def mean(values: Sequence[float | None]) -> float | None:
    """The mean of the values that aren't None; None when there are none."""
    known = [value for value in values if value is not None]
    return sum(known) / len(known) if known else None


def percentile(values: Sequence[float], q: float) -> float | None:
    """The nearest-rank percentile (q from 0 to 100): a value that was measured, never an
    interpolation. None for no values."""
    if not values:
        return None
    if not 0 <= q <= 100:
        raise ValueError("q must be between 0 and 100")
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100 * len(ordered)))
    return ordered[rank - 1]
