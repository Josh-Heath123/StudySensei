"""A paper's text, and each part's own text cut from it at the segmenter's ``first_words``.

Pure functions (unit-tested). The cut is what classification C2 embeds and sends: a part's
text runs from its anchor to the next part's anchor (at most ``MAX_PART_CHARS``), after its
question's stem (the text just before the question's first part, at most ``STEM_CHARS``).
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

MAX_PART_CHARS = 1200
STEM_CHARS = 400
# A page whose text layer is shorter than this is transcribed (a title over a scanned image).
NEARLY_EMPTY_CHARS = 200
_WORD = re.compile(r"[a-z0-9]+")


def needs_transcription(is_scanned: bool, char_count: int) -> bool:
    return is_scanned or char_count < NEARLY_EMPTY_CHARS


@dataclass(frozen=True)
class Anchor:
    number: str
    parent: str | None
    first_words: str


@dataclass(frozen=True)
class Cut:
    number: str
    text: str
    found: bool  # whether the anchor was found in the text


def _words(text: str) -> list[tuple[str, int]]:
    """Lower-case words with their start offsets."""
    return [(m.group(), m.start()) for m in _WORD.finditer(text.lower())]


def find_anchor(words: Sequence[tuple[str, int]], first_words: str, start: int) -> int | None:
    """The word index where ``first_words`` (up to its first 6 words) begins, at or after
    word ``start``; a shorter prefix (down to 3 words) is tried when the whole isn't found."""
    wanted = _WORD.findall(first_words.lower())[:6]
    tokens = [w for w, _ in words]
    for size in range(len(wanted), min(3, len(wanted)) - 1, -1):
        probe = wanted[:size]
        if not probe:
            break
        for i in range(start, len(tokens) - size + 1):
            if tokens[i : i + size] == probe:
                return i
    return None


def cut_parts(text: str, anchors: Sequence[Anchor]) -> list[Cut]:
    words = _words(text)
    positions: list[int | None] = []
    cursor = 0
    for anchor in anchors:
        at = find_anchor(words, anchor.first_words, cursor)
        positions.append(at)
        if at is not None:
            cursor = at + 1
    offsets = [words[p][1] if p is not None else None for p in positions]
    cuts: list[Cut] = []
    first_of_parent: dict[str | None, int] = {}
    for i, anchor in enumerate(anchors):
        start = offsets[i]
        if start is None:
            cuts.append(Cut(anchor.number, anchor.first_words, False))
            continue
        later = [o for o in offsets[i + 1 :] if o is not None and o > start]
        end = min(later[0] if later else len(text), start + MAX_PART_CHARS)
        own = text[start:end]
        key = anchor.parent if anchor.parent is not None else anchor.number
        stem_at = first_of_parent.setdefault(key, start)
        stem = text[max(0, stem_at - STEM_CHARS) : stem_at] if anchor.parent is not None else ""
        cuts.append(Cut(anchor.number, f"{stem}\n{own}".strip(), True))
    return cuts
