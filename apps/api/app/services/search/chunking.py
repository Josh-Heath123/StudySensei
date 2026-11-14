"""Split one page's text into chunks the embedding model can read whole (decision 0005).

Pure functions: tokens are counted by the function passed in, which in the app is
the embedding model's own tokenizer, so a chunk never gets cut off by the model.

- A chunk never spans two pages: the chunker only ever sees one page.
- A page that fits in ``max_tokens`` is one chunk.
- A longer page is split at paragraphs (blank lines), then lines, then sentences,
  then words, only as far down as needed. Pieces are packed greedily up to
  ``max_tokens``, and each chunk after the first starts with up to ``overlap``
  tokens from the end of the one before (at a sentence boundary when one fits).
- Chunks are slices of the page text, so their text is exactly as it was on the page.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

CountTokens = Callable[[str], int]

MAX_TOKENS = 400
OVERLAP_TOKENS = 50
# Most of a title is enough context, and keeps the embedded text well under 512 tokens.
_TITLE_CHARS = 150

# Boundaries from coarsest to finest. Each pattern matches the gap between two pieces.
_PARAGRAPHS = re.compile(r"\n[ \t]*\n\s*")
_LINES = re.compile(r"\s*\n\s*")
_SENTENCES = re.compile(r"(?<=[.!?;:])\s+")
_WORDS = re.compile(r"\s+")
_LEVELS = (_PARAGRAPHS, _LINES, _SENTENCES, _WORDS)


@dataclass(frozen=True)
class Span:
    """``text[start:end]`` of the page."""

    start: int
    end: int


def _pieces(text: str, start: int, end: int, gap: re.Pattern[str]) -> list[Span]:
    """Split ``text[start:end]`` at ``gap``, dropping empty pieces and surrounding whitespace."""
    spans: list[Span] = []
    position = start
    for match in gap.finditer(text, start, end):
        spans.append(Span(position, match.start()))
        position = match.end()
    spans.append(Span(position, end))
    return [trimmed for span in spans if (trimmed := _trim(text, span)) is not None]


def _trim(text: str, span: Span) -> Span | None:
    piece = text[span.start : span.end]
    stripped = piece.lstrip()
    start = span.start + len(piece) - len(stripped)
    end = start + len(stripped.rstrip())
    return Span(start, end) if end > start else None


def _atoms(text: str, span: Span, count: CountTokens, limit: int, level: int = 0) -> list[Span]:
    """Pieces of ``span`` that each fit in ``limit`` (a single word that doesn't stays whole)."""
    if level >= len(_LEVELS) or count(text[span.start : span.end]) <= limit:
        return [span]
    pieces = _pieces(text, span.start, span.end, _LEVELS[level])
    return [atom for piece in pieces for atom in _atoms(text, piece, count, limit, level + 1)]


def _overlap_start(text: str, chunk: Span, count: CountTokens, overlap: int) -> int | None:
    """Where the next chunk's overlap begins: the longest tail of ``chunk`` within ``overlap``.

    Tries sentence starts first, then word starts. None if not even one word fits.
    """
    for gap in (_SENTENCES, _WORDS):
        starts = [piece.start for piece in _pieces(text, chunk.start, chunk.end, gap)][1:]
        best = None
        for start in reversed(starts):
            if count(text[start : chunk.end]) > overlap:
                break
            best = start
        if best is not None:
            return best
    return None


def chunk_page(
    text: str,
    count: CountTokens,
    *,
    max_tokens: int = MAX_TOKENS,
    overlap: int = OVERLAP_TOKENS,
) -> list[str]:
    """The page's chunks, in order. Empty if the page has no text."""
    return [text[span.start : span.end] for span in chunk_spans(text, count, max_tokens, overlap)]


def chunk_spans(text: str, count: CountTokens, max_tokens: int, overlap: int) -> list[Span]:
    whole = _trim(text, Span(0, len(text)))
    if whole is None:
        return []
    atoms = _atoms(text, whole, count, max_tokens)
    chunks: list[Span] = []
    start = atoms[0].start
    i = 0  # the first atom not yet in any chunk
    while i < len(atoms):
        # Always take at least one new atom, then as many more as fit.
        if count(text[start : atoms[i].end]) > max_tokens:
            start = atoms[i].start  # the overlap and this atom don't fit together: drop the overlap
        j = i + 1
        while j < len(atoms) and count(text[start : atoms[j].end]) <= max_tokens:
            j += 1
        chunk = Span(start, atoms[j - 1].end)
        chunks.append(chunk)
        i = j
        if i < len(atoms):
            tail = _overlap_start(text, chunk, count, overlap) if overlap > 0 else None
            start = tail if tail is not None else atoms[i].start
    return chunks


def embedding_text(material_title: str, page_title: str | None, text: str) -> str:
    """What gets embedded: the material's name and the page title, then the chunk text.

    E.g. "CH03 · User authentication". The stored chunk text stays as it was on the page.
    """
    heading = material_title.strip()[:_TITLE_CHARS]
    if page_title and page_title.strip():
        heading = f"{heading} · {page_title.strip()[:_TITLE_CHARS]}"
    return f"{heading}\n\n{text}" if heading else text
