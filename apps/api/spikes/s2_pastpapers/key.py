"""The answer key, ``evals/pastpapers/<name>.yaml`` (metadata only, no question text)."""

from dataclasses import dataclass
from typing import Any

from evals.common import load_config
from spikes.s2_pastpapers.metrics import KeyPart, normalise

TYPES = ("recall", "explain", "apply", "calculate", "essay")


@dataclass(frozen=True)
class Box:
    """A box painted out of a page image, in fractions of the page."""

    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True)
class KeyPaper:
    label: str
    title: str
    printed_total: float | None
    excluded_pages: frozenset[int]
    mask: dict[int, tuple[Box, ...]]
    parts: tuple[KeyPart, ...]

    @property
    def marks_sum(self) -> float:
        return sum(p.marks for p in self.parts)


@dataclass(frozen=True)
class Key:
    module: str
    papers: tuple[KeyPaper, ...]
    excluded_titles: frozenset[str]
    raw: dict[str, Any]


def _part(raw: dict[str, Any]) -> KeyPart:
    topics = list(raw["topics"])
    if raw["type"] not in TYPES:
        raise ValueError(f"{raw['number']}: unknown type {raw['type']!r}")
    if not topics or len(topics) > 3:
        raise ValueError(f"{raw['number']}: 1 to 3 topics, the chapter first")
    return KeyPart(
        number=str(raw["number"]),
        marks=float(raw["marks"]),
        page=int(raw["page"]),
        type=raw["type"],
        chapter=topics[0],
        subtopics=tuple(topics[1:]),
        weak=raw.get("fit") == "weak",
    )


def parse_key(raw: dict[str, Any]) -> Key:
    papers = []
    for paper in raw["papers"]:
        mask = {
            int(page): tuple(Box(*map(float, box)) for box in boxes)
            for page, boxes in (paper.get("mask") or {}).items()
        }
        papers.append(
            KeyPaper(
                label=paper["label"],
                title=paper["title"],
                printed_total=paper.get("printed_total"),
                excluded_pages=frozenset(paper.get("excluded_pages") or ()),
                mask=mask,
                parts=tuple(_part(p) for p in paper["parts"]),
            )
        )
    return Key(
        module=raw["module"],
        papers=tuple(papers),
        excluded_titles=frozenset(p["title"] for p in raw.get("excluded_papers") or ()),
        raw=raw,
    )


def load_key(name: str) -> Key:
    return parse_key(load_config(f"pastpapers/{name}.yaml"))


def check_key(
    key: Key, chapters: set[str] | None = None, subtopics: set[str] | None = None
) -> list[str]:
    """Problems with the key: a sum that isn't the printed total, a part on an excluded
    page, a repeated number, and (given the tree's names) a topic not in the tree."""

    problems: list[str] = []
    for paper in key.papers:
        if paper.printed_total is not None and paper.marks_sum != paper.printed_total:
            problems.append(
                f"{paper.label}: parts sum to {paper.marks_sum:g}, printed {paper.printed_total:g}"
            )
        seen: set[str] = set()
        for part in paper.parts:
            n = normalise(part.number)
            if n in seen:
                problems.append(f"{paper.label} {part.number}: listed twice")
            seen.add(n)
            if part.page in paper.excluded_pages:
                problems.append(f"{paper.label} {part.number}: on an excluded page")
            if chapters is not None and part.chapter not in chapters:
                problems.append(f"{paper.label} {part.number}: chapter not in the tree")
            if subtopics is not None:
                problems += [
                    f"{paper.label} {part.number}: subtopic not in the tree"
                    for s in part.subtopics
                    if s not in subtopics
                ]
    return problems
