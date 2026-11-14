"""A deterministic stand-in for the embedding model, so tests never download it."""

import hashlib
import math
import re
from collections.abc import Sequence

from app.services.search.embedding import DIMENSIONS

_TOKENS = re.compile(r"\w+|[^\w\s]")
_WORDS = re.compile(r"\w+")


class FakeEmbedder:
    """Bag of words hashed into 384 dimensions, normalised.

    Texts sharing words get close vectors, so vector ranking is meaningful in tests.
    Tokens are words and punctuation marks, roughly like a WordPiece tokenizer.
    """

    def __init__(self) -> None:
        self.passages: list[str] = []
        self.passage_calls: list[int] = []
        self.query_calls: list[str] = []

    def count_tokens(self, text: str) -> int:
        return len(_TOKENS.findall(text))

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * DIMENSIONS
        for word in _WORDS.findall(text.lower()):
            digest = hashlib.blake2b(word.encode(), digest_size=4).digest()
            vector[int.from_bytes(digest) % DIMENSIONS] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            vector[0], norm = 1.0, 1.0
        return [value / norm for value in vector]

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        self.passage_calls.append(len(texts))
        self.passages.extend(texts)
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        self.query_calls.append(text)
        return self._vector(text)
