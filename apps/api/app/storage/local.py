"""Storage in a local folder (``data/materials`` in development)."""

import os
from functools import lru_cache
from pathlib import Path
from typing import BinaryIO

from app.core.config import get_settings
from app.storage.base import Storage, check_key


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path_for(self, key: str) -> Path:
        check_key(key)  # only "{uuid}/{hex}": nothing can point outside the root
        return self.root / key

    def put(self, key: str, source: Path) -> None:
        target = self.path_for(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Move into the same folder first, then rename: readers never see half a file.
        staging = target.with_name(f".{target.name}.part")
        try:
            os.replace(source, staging)
        except OSError:  # a different drive or filesystem: copy instead
            _copy(source, staging)
        os.replace(staging, target)

    def exists(self, key: str) -> bool:
        return self.path_for(key).is_file()

    def open(self, key: str) -> BinaryIO:
        return self.path_for(key).open("rb")

    def delete(self, key: str) -> None:
        self.path_for(key).unlink(missing_ok=True)


def _copy(source: Path, target: Path) -> None:
    with source.open("rb") as src, target.open("wb") as dst:
        while chunk := src.read(1024 * 1024):
            dst.write(chunk)
    source.unlink()


@lru_cache
def _default_storage() -> LocalStorage:
    return LocalStorage(get_settings().storage_dir)


def get_storage() -> Storage:
    """FastAPI dependency (tests override it with a temporary folder)."""
    return _default_storage()
