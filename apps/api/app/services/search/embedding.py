"""Local text embeddings with fastembed (decision 0005).

The model (BAAI/bge-small-en-v1.5, 384 dimensions, normalised vectors) runs on the
CPU, so no text leaves the machine. It's loaded once per process, on first use, and
cached under ``data/models`` (gitignored). The first run downloads it.

Tests replace it with a deterministic fake via ``set_embedder``.
"""

import logging
import threading
import warnings
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings
from app.models.materials import EMBEDDING_DIMENSIONS

log = logging.getLogger("studysensei.embedding")

MODEL_NAME = "BAAI/bge-small-en-v1.5"
DIMENSIONS = EMBEDDING_DIMENSIONS
# The model reads at most 512 tokens, two of which are [CLS] and [SEP].
MAX_INPUT_TOKENS = 510
BATCH_SIZE = 32


class Embedder(Protocol):
    """Turns text into unit vectors of ``DIMENSIONS`` floats, and counts its tokens."""

    def count_tokens(self, text: str) -> int:
        """Tokens in ``text`` by the model's own tokenizer, without special tokens."""
        ...

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        """Vectors for stored chunks."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """The vector for a search (bge adds its query instruction)."""
        ...


class FastEmbedder:
    """The real model. Construct it once per process (``get_embedder`` does)."""

    def __init__(self, cache_dir: Path) -> None:
        from fastembed import TextEmbedding
        from tokenizers import Tokenizer

        cache_dir.mkdir(parents=True, exist_ok=True)
        if not any("bge-small-en-v1.5" in entry.name for entry in cache_dir.iterdir()):
            log.warning(
                "Downloading the embedding model %s (about 70 MB) to %s. This happens once.",
                MODEL_NAME,
                cache_dir,
            )
        with warnings.catch_warnings():
            # huggingface_hub warns that Windows can't make symlinks; the cache still works.
            warnings.filterwarnings("ignore", message=".*symlinks.*", category=UserWarning)
            self._model = TextEmbedding(MODEL_NAME, cache_dir=str(cache_dir))
        # The model's tokenizer truncates at 512; counting needs the full length.
        self._tokenizer = Tokenizer.from_str(self._model.model.tokenizer.to_str())  # type: ignore[attr-defined]
        self._tokenizer.no_truncation()
        self._tokenizer.no_padding()
        log.info("Embedding model %s loaded", MODEL_NAME)

    def count_tokens(self, text: str) -> int:
        return len(self._tokenizer.encode(text, add_special_tokens=False).ids)

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = self._model.passage_embed(list(texts), batch_size=BATCH_SIZE)
        return [vector.tolist() for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        vector = next(iter(self._model.query_embed(text)))
        return list(vector.tolist())


_embedder: Embedder | None = None
_lock = threading.Lock()


def get_embedder() -> Embedder:
    """The process's embedder, loaded on first use (slow: call it from a thread)."""
    global _embedder
    with _lock:
        if _embedder is None:
            _embedder = FastEmbedder(get_settings().models_dir)
        return _embedder


def set_embedder(embedder: Embedder | None) -> None:
    """Replace the process's embedder (tests use a fake); None loads the real one again."""
    global _embedder
    with _lock:
        _embedder = embedder
