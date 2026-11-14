"""Build a material's chunks with their embeddings (the index_material job's work)."""

from collections.abc import Sequence
from dataclasses import dataclass

from app.services.search.chunking import chunk_page, embedding_text
from app.services.search.embedding import MAX_INPUT_TOKENS, Embedder


@dataclass(frozen=True)
class PageText:
    number: int
    title: str | None
    text: str


@dataclass(frozen=True)
class NewChunk:
    page_number: int
    position: int
    text: str
    token_count: int
    embedding: list[float]


def _fitted(embedder: Embedder, material_title: str, page: PageText, text: str) -> str:
    """The text to embed, dropping titles if they'd push it past the model's limit."""
    for candidate in (
        embedding_text(material_title, page.title, text),
        embedding_text(material_title, None, text),
    ):
        if embedder.count_tokens(candidate) <= MAX_INPUT_TOKENS:
            return candidate
    return text


def build_chunks(
    embedder: Embedder, material_title: str, pages: Sequence[PageText]
) -> list[NewChunk]:
    """Chunk every page and embed the chunks in batches. Slow: run it in a thread."""
    pieces: list[tuple[PageText, int, str]] = []
    for page in pages:
        for position, text in enumerate(chunk_page(page.text, embedder.count_tokens)):
            pieces.append((page, position, text))
    if not pieces:
        return []
    vectors = embedder.embed_passages(
        [_fitted(embedder, material_title, page, text) for page, _, text in pieces]
    )
    return [
        NewChunk(
            page_number=page.number,
            position=position,
            text=text,
            token_count=embedder.count_tokens(text),
            embedding=vector,
        )
        for (page, position, text), vector in zip(pieces, vectors, strict=True)
    ]
