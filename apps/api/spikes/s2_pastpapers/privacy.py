"""Privacy before any AI call (spike S2, part 1).

- The owner's own submissions are recognised by the file pattern in ``CLAUDE.local.md``
  (gitignored, on the owner's machine only). It is read at run time, never written into a
  tracked file. A past paper or test matching it, by title, file name or content hash
  (against the matching files in the course folder), is excluded and never read.
- Pages with someone's answers, marking or identity are listed in the key
  (``excluded_pages``, ``excluded_papers``) after reading every page by hand.
- Names printed on a paper (examiners, staff) are redacted from text and masked on images
  before anything is sent.
"""

import fnmatch
import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image as PILImage
from PIL import ImageDraw

from spikes.s2_pastpapers.key import Box

REPO_ROOT = Path(__file__).resolve().parents[4]
LOCAL_NOTES = REPO_ROOT / "CLAUDE.local.md"

_TITLE = r"(?:Prof|Professor|Dr|Mr|Mrs|Ms|Miss)\.?"
_NAME = r"(?:\s+(?:[A-Z]\.\s*)*[A-Z][a-z'\-]+){1,3}"
_INITIALS = r"(?:\s+(?:[A-Z]\.?\s*){1,3})?"
STAFF_NAME = re.compile(rf"\b{_TITLE}{_INITIALS}{_NAME}")
EXAMINER_LINE = re.compile(r"(?im)^(.*\bexaminers?\b\s*:?).*$")
REDACTED = "[name]"


@dataclass(frozen=True)
class LocalPrivacy:
    course_folder: Path
    submission_pattern: str


def read_local_privacy(path: Path = LOCAL_NOTES) -> LocalPrivacy:
    """The course folder and the submissions' file pattern, from ``CLAUDE.local.md``."""
    if not path.is_file():
        raise SystemExit(f"{path.name} is missing: the privacy check needs it.")
    text = path.read_text(encoding="utf-8")
    folder = re.search(r"course material\*\*.*?`([^`]+)`", text, re.S)
    pattern = re.search(r"own submissions:\*\*.*?`([^`]+)`", text, re.S)
    if folder is None or pattern is None:
        raise SystemExit(f"Couldn't find the course folder and pattern in {path.name}.")
    return LocalPrivacy(Path(folder.group(1)), pattern.group(1))


def is_submission(name: str, pattern: str) -> bool:
    return fnmatch.fnmatch(name.lower(), pattern.lower())


def submission_hashes(local: LocalPrivacy) -> set[str]:
    """SHA-256 of every file in the course folder matching the pattern (read only to hash)."""
    found: set[str] = set()
    for path in local.course_folder.rglob("*"):
        if path.is_file() and is_submission(path.name, local.submission_pattern):
            found.add(hashlib.sha256(path.read_bytes()).hexdigest())
    return found


def redact_text(text: str) -> str:
    """Names with a title ("Prof A. B. Name") and the rest of an "Examiner:" line."""
    text = EXAMINER_LINE.sub(lambda m: f"{m.group(1)} {REDACTED}", text)
    return STAFF_NAME.sub(REDACTED, text)


def mask_png(png: bytes, boxes: tuple[Box, ...]) -> bytes:
    """The page image with each box painted white."""
    if not boxes:
        return png
    image = PILImage.open(io.BytesIO(png)).convert("RGB")
    draw = ImageDraw.Draw(image)
    w, h = image.size
    for box in boxes:
        draw.rectangle((box.x0 * w, box.y0 * h, box.x1 * w, box.y1 * h), fill="white")
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()
