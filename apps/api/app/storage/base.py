"""Where uploaded files live.

Keys are ``{user_id}/{sha256}``: one blob per distinct file per user, so the same
file uploaded twice is stored once, and nothing is shared between accounts.
"""

import re
import uuid
from pathlib import Path
from typing import BinaryIO, Protocol

_KEY = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/[0-9a-f]{64}$")


class InvalidKey(ValueError):
    """A key that isn't ``{user uuid}/{sha256 hex}`` (and so might escape the storage root)."""


def blob_key(user_id: uuid.UUID, sha256: str) -> str:
    key = f"{user_id}/{sha256}"
    check_key(key)
    return key


def check_key(key: str) -> None:
    if not _KEY.fullmatch(key):
        raise InvalidKey(f"Not a storage key: {key!r}")


class Storage(Protocol):
    def put(self, key: str, source: Path) -> None:
        """Store the file at ``source`` under ``key`` (moved, not copied). Atomic."""
        ...

    def exists(self, key: str) -> bool: ...

    def open(self, key: str) -> BinaryIO:
        """Open the blob for reading. Raises FileNotFoundError if it's missing."""
        ...

    def path_for(self, key: str) -> Path:
        """A local path to the blob, for libraries that need one (e.g. pypdfium2)."""
        ...

    def delete(self, key: str) -> None:
        """Remove the blob; a missing one is fine."""
        ...
