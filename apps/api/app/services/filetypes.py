"""Which files can be uploaded, checked by their content as well as their name.

A file whose bytes don't match its extension (a renamed executable, say) is
refused, so later steps can trust the type they're given.
"""

import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Literal

FileType = Literal["pdf", "pptx", "docx", "md", "txt", "png", "jpg"]


@dataclass(frozen=True)
class AllowedType:
    type: FileType
    content_type: str


ALLOWED: dict[str, AllowedType] = {
    ".pdf": AllowedType("pdf", "application/pdf"),
    ".pptx": AllowedType(
        "pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ),
    ".docx": AllowedType(
        "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
    ".md": AllowedType("md", "text/markdown"),
    ".txt": AllowedType("txt", "text/plain"),
    ".png": AllowedType("png", "image/png"),
    ".jpg": AllowedType("jpg", "image/jpeg"),
    ".jpeg": AllowedType("jpg", "image/jpeg"),
}

ALLOWED_EXTENSIONS = sorted(ALLOWED)
_PNG = b"\x89PNG\r\n\x1a\n"
_JPEG = b"\xff\xd8\xff"


class NotAllowed(ValueError):
    """The file's type isn't allowed, or its content doesn't match its name."""


def detect(filename: str, path: Path) -> AllowedType:
    """The file's allowed type, checked against its first bytes. Raises NotAllowed."""
    extension = PurePath(filename).suffix.lower()
    allowed = ALLOWED.get(extension)
    if allowed is None:
        raise NotAllowed(
            f"{extension or 'Files without an extension'} can't be uploaded. "
            "Use PDF, PPTX, DOCX, MD, TXT, PNG or JPG."
        )
    if not _content_matches(allowed.type, path):
        raise NotAllowed(f"The file's content doesn't look like {extension[1:].upper()}.")
    return allowed


def _content_matches(kind: FileType, path: Path) -> bool:
    with path.open("rb") as f:
        head = f.read(8)
    match kind:
        case "pdf":
            return head.startswith(b"%PDF-")
        case "png":
            return head.startswith(_PNG)
        case "jpg":
            return head.startswith(_JPEG)
        case "pptx":
            return _office_zip(path, "ppt/")
        case "docx":
            return _office_zip(path, "word/")
        case "md" | "txt":
            return _plain_text(path)


def _office_zip(path: Path, folder: str) -> bool:
    if not zipfile.is_zipfile(path):
        return False
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
    except zipfile.BadZipFile:
        return False
    return "[Content_Types].xml" in names and any(name.startswith(folder) for name in names)


def _plain_text(path: Path) -> bool:
    data = path.read_bytes()
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True
