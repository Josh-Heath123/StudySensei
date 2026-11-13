"""The upload allow-list, checked by content as well as by name."""

from pathlib import Path

import pytest

from app.services.filetypes import NotAllowed, detect
from tests.materials import samples


def written(tmp_path: Path, data: bytes) -> Path:
    path = tmp_path / "upload"
    path.write_bytes(data)
    return path


@pytest.mark.parametrize(
    ("filename", "data", "kind", "content_type"),
    [
        ("Week 3.pdf", samples.pdf(1), "pdf", "application/pdf"),
        (
            "Deck.PPTX",
            samples.pptx(),
            "pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ),
        (
            "Notes.docx",
            samples.docx(),
            "docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        ("notes.md", samples.MD, "md", "text/markdown"),
        ("notes.txt", samples.TXT, "txt", "text/plain"),
        ("diagram.png", samples.PNG, "png", "image/png"),
        ("photo.jpg", samples.JPG, "jpg", "image/jpeg"),
        ("photo.jpeg", samples.JPG, "jpg", "image/jpeg"),
    ],
)
def test_allowed_types_are_detected(
    tmp_path: Path, filename: str, data: bytes, kind: str, content_type: str
) -> None:
    allowed = detect(filename, written(tmp_path, data))
    assert (allowed.type, allowed.content_type) == (kind, content_type)


@pytest.mark.parametrize(
    ("filename", "data", "message"),
    [
        ("setup.exe", b"MZ\x90\x00", ".exe can't be uploaded"),
        ("archive.zip", samples.pptx(), ".zip can't be uploaded"),
        ("README", samples.TXT, "Files without an extension can't be uploaded"),
        ("slides.pdf", samples.PNG, "doesn't look like PDF"),
        ("deck.pptx", samples.docx(), "doesn't look like PPTX"),
        ("notes.docx", samples.pptx(), "doesn't look like DOCX"),
        ("notes.docx", b"PK\x03\x04 not really a zip", "doesn't look like DOCX"),
        ("notes.txt", b"binary\x00data", "doesn't look like TXT"),
        ("notes.md", b"\xff\xfe\xfa not utf-8", "doesn't look like MD"),
        ("photo.png", samples.JPG, "doesn't look like PNG"),
    ],
)
def test_wrong_types_and_mismatched_content_are_refused(
    tmp_path: Path, filename: str, data: bytes, message: str
) -> None:
    with pytest.raises(NotAllowed, match=message):
        detect(filename, written(tmp_path, data))
