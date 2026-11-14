"""Schemas for module search."""

import uuid

from pydantic import BaseModel, ConfigDict


class SnippetPart(BaseModel):
    """A run of snippet text; ``highlight`` marks words that matched the query."""

    model_config = ConfigDict(from_attributes=True)

    text: str
    highlight: bool


class SearchResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: uuid.UUID
    material_id: uuid.UUID
    material_title: str
    original_filename: str
    page_number: int
    page_title: str | None
    # The chunk's place on its page (0 first).
    position: int
    # The chunk's text, exactly as on the page.
    text: str
    # The part of the text around the matched words (from the start when only the meaning matched).
    snippet: list[SnippetPart]
    # Reciprocal rank fusion score: higher is better. For ordering, not for showing.
    score: float
    # Where the chunk ranked by meaning (vector) and by words (keyword), if in the top 20.
    vector_rank: int | None
    keyword_rank: int | None


class SearchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    query: str
    results: list[SearchResult]
    # How many chunks the module has. 0 means nothing is indexed yet.
    indexed_chunks: int
