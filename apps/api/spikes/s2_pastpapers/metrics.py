"""Scoring S2's candidates against the answer key (pure functions, unit-tested).

- **Numbers** are compared normalised: lower case, the runs of digits and letters joined
  with dots, a leading "q"/"question" dropped. "1.1(a)", "1.1a" and "Q1.1 (a)" are all
  "1.1.a"; "1a.ii" is "1.a.ii".
- **Segmentation exact:** a key part counts when a predicted part has its number and its
  marks. Predicted parts that match no key number are counted as extra.
- **Topic agreement**, per part the classifier answered: chapter-level when the predicted
  primary chapter (the chapter of its first topic) is the key's chapter; subtopic-level when
  the Jaccard index of the subtopic sets is at least 0.5 (a side with no subtopics stands
  for its chapter, so two chapter-only answers agree when the chapters match).
- **Type agreement:** the same type.
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

JACCARD_AGREES = 0.5
_TOKENS = re.compile(r"[0-9]+|[a-z]+")
_PREFIXES = ("question", "q", "vraag")


def normalise(number: str) -> str:
    tokens = _TOKENS.findall(number.lower())
    while tokens and tokens[0] in _PREFIXES:
        tokens = tokens[1:]
    return ".".join(tokens)


def qualify(number: str, parent: str | None) -> str:
    """The full number: a bare label ("a", "(b)", "2") under a parent ("3") becomes "3.a",
    "3.b", "3.2"; a number that already starts with its parent is kept. Code, not the model,
    so a reply that gives only the local label still lands on the right part."""
    if not parent:
        return number
    own, head = normalise(number), normalise(parent)
    if not head or own == head or own.startswith(head + "."):
        return number
    return f"{head}.{own}"


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    left, right = set(a), set(b)
    if not left and not right:
        return 1.0
    return len(left & right) / len(left | right)


def pct(part: int, whole: int) -> float | None:
    return round(100 * part / whole, 1) if whole else None


@dataclass(frozen=True)
class KeyPart:
    number: str
    marks: float
    page: int
    type: str
    chapter: str
    subtopics: tuple[str, ...]
    weak: bool = False


@dataclass(frozen=True)
class Predicted:
    number: str
    marks: float
    page: int | None = None


@dataclass
class SegmentationScore:
    parts: int
    exact: int
    number_only: int  # the number was found but the marks differ
    missing: int
    extra: int
    page_right: int
    total_right: bool | None  # None when the paper prints no total
    sum_right: bool  # the predicted parts' marks add up to the key's sum
    mismatches: list[str] = field(default_factory=list)  # numbers only

    @property
    def exact_pct(self) -> float | None:
        return pct(self.exact, self.parts)


def score_segmentation(
    key: Sequence[KeyPart],
    predicted: Sequence[Predicted],
    *,
    printed_total: float | None,
    predicted_total: float | None,
) -> SegmentationScore:
    by_number: dict[str, list[Predicted]] = {}
    for p in predicted:
        by_number.setdefault(normalise(p.number), []).append(p)
    exact = number_only = missing = page_right = 0
    mismatches: list[str] = []
    for part in key:
        found = by_number.get(normalise(part.number), [])
        if not found:
            missing += 1
            mismatches.append(f"{part.number}: missing")
            continue
        best = next((p for p in found if p.marks == part.marks), None)
        if best is None:
            number_only += 1
            mismatches.append(f"{part.number}: marks {found[0].marks:g} not {part.marks:g}")
            best = found[0]
        else:
            exact += 1
        if best.page == part.page:
            page_right += 1
    key_numbers = {normalise(k.number) for k in key}
    extra = sum(len(v) for n, v in by_number.items() if n not in key_numbers)
    extra += sum(len(v) - 1 for n, v in by_number.items() if n in key_numbers)
    mismatches += [f"{n}: extra" for n in by_number if n not in key_numbers]
    return SegmentationScore(
        parts=len(key),
        exact=exact,
        number_only=number_only,
        missing=missing,
        extra=extra,
        page_right=page_right,
        total_right=None if printed_total is None else predicted_total == printed_total,
        sum_right=sum(p.marks for p in predicted) == sum(k.marks for k in key),
        mismatches=mismatches,
    )


@dataclass(frozen=True)
class Classified:
    number: str
    chapter: str  # the chapter of the first topic
    subtopics: tuple[str, ...]
    type: str


@dataclass
class ClassificationScore:
    parts: int  # key parts
    answered: int  # key parts the classifier gave topics for
    chapter_agree: int
    subtopic_agree: int
    type_agree: int
    # The same three over the parts whose key topic fits well (not "weak").
    strong_answered: int
    strong_chapter_agree: int
    strong_subtopic_agree: int

    def as_dict(self) -> dict[str, object]:
        return {
            "parts": self.parts,
            "answered": self.answered,
            "chapter_agree": self.chapter_agree,
            "chapter_pct": pct(self.chapter_agree, self.answered),
            "subtopic_agree": self.subtopic_agree,
            "subtopic_pct": pct(self.subtopic_agree, self.answered),
            "type_agree": self.type_agree,
            "type_pct": pct(self.type_agree, self.answered),
            "strong_answered": self.strong_answered,
            "strong_chapter_pct": pct(self.strong_chapter_agree, self.strong_answered),
            "strong_subtopic_pct": pct(self.strong_subtopic_agree, self.strong_answered),
        }


def subtopic_set(chapter: str, subtopics: Sequence[str]) -> set[str]:
    return set(subtopics) if subtopics else {chapter}


def score_classification(
    key: Sequence[KeyPart], classified: Mapping[str, Classified]
) -> ClassificationScore:
    """``classified`` is keyed by normalised number."""
    answered = chapter = sub = kind = 0
    s_answered = s_chapter = s_sub = 0
    for part in key:
        got = classified.get(normalise(part.number))
        if got is None:
            continue
        answered += 1
        same_chapter = got.chapter == part.chapter
        same_sub = (
            jaccard(
                subtopic_set(part.chapter, part.subtopics),
                subtopic_set(got.chapter, got.subtopics),
            )
            >= JACCARD_AGREES
        )
        chapter += same_chapter
        sub += same_sub
        kind += got.type == part.type
        if not part.weak:
            s_answered += 1
            s_chapter += same_chapter
            s_sub += same_sub
    return ClassificationScore(
        parts=len(key),
        answered=answered,
        chapter_agree=chapter,
        subtopic_agree=sub,
        type_agree=kind,
        strong_answered=s_answered,
        strong_chapter_agree=s_chapter,
        strong_subtopic_agree=s_sub,
    )


# --- transcription check ---------------------------------------------------------------


def label_found(text: str, number: str) -> bool:
    """Whether the part's own label (its last token) appears as a label in ``text``:
    "a)", "(a)", "a.", "ii)", or "Question 3" / "3." for a whole question."""
    tokens = normalise(number).split(".")
    last = re.escape(tokens[-1])
    lowered = text.lower()
    if len(tokens) == 1:
        return bool(re.search(rf"(question\s*{last}\b|(?<![\w.]){last}[.)])", lowered))
    return bool(re.search(rf"(?<![\w])\(?{last}[).](?!\d)", lowered))


def marks_found(text: str, marks: float) -> bool:
    """Whether the marks appear as marks: "(5)", "[5]", "5 marks", "(1 mark)"."""
    m = re.escape(f"{marks:g}")
    pattern = rf"[\(\[]\s*{m}\s*(marks?)?\s*[\)\]]|(?<![\d.]){m}\s*marks?\b"
    return bool(re.search(pattern, text.lower()))
