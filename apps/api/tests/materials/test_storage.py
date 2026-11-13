"""The local-folder Storage: atomic puts, safe keys."""

import uuid
from pathlib import Path

import pytest

from app.storage.base import InvalidKey, blob_key
from app.storage.local import LocalStorage

USER = uuid.UUID("00000000-0000-4000-8000-000000000001")
SHA = "a" * 64


def make_file(tmp_path: Path, data: bytes) -> Path:
    path = tmp_path / f"upload-{uuid.uuid4().hex}"
    path.write_bytes(data)
    return path


def test_put_open_and_delete(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "store")
    key = blob_key(USER, SHA)
    source = make_file(tmp_path, b"hello")

    storage.put(key, source)

    assert storage.exists(key)
    assert not source.exists()  # moved, not copied
    with storage.open(key) as f:
        assert f.read() == b"hello"
    assert storage.path_for(key) == tmp_path / "store" / str(USER) / SHA
    # No staging file is left behind.
    assert [p.name for p in storage.path_for(key).parent.iterdir()] == [SHA]

    storage.delete(key)
    assert not storage.exists(key)
    storage.delete(key)  # deleting a missing blob is fine


def test_put_replaces_an_existing_blob_whole(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "store")
    key = blob_key(USER, SHA)
    storage.put(key, make_file(tmp_path, b"first"))
    storage.put(key, make_file(tmp_path, b"second"))

    with storage.open(key) as f:
        assert f.read() == b"second"


@pytest.mark.parametrize(
    "key",
    [
        "../etc/passwd",
        f"{USER}/../{SHA}",
        f"{USER}/{SHA}/x",
        f"{USER}/{'A' * 64}",
        f"{USER}/{'a' * 63}",
        f"/{USER}/{SHA}",
        "",
    ],
)
def test_keys_that_could_escape_the_root_are_refused(tmp_path: Path, key: str) -> None:
    storage = LocalStorage(tmp_path / "store")
    with pytest.raises(InvalidKey):
        storage.path_for(key)
    with pytest.raises(InvalidKey):
        storage.exists(key)


def test_missing_blob_raises_on_open(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "store")
    with pytest.raises(FileNotFoundError):
        storage.open(blob_key(USER, SHA))
