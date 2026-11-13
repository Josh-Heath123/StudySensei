"""Text extraction: a stored file → its text, page by page.

Pure and synchronous (the worker runs it in a thread). A "page" is a PDF page, a
slide (title, body and speaker notes), or a section of a document split at
headings or about every 800 words. Images become one page with no text.

Anything unreadable raises ``ExtractionError`` with a message for people, never
a library's stack trace.
"""

import logging
import re
import zipfile
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from pptx import Presentation
from pptx.exc import PackageNotFoundError as PptxPackageError
from pptx.shapes.autoshape import Shape
from pptx.shapes.base import BaseShape
from pptx.shapes.graphfrm import GraphicFrame
from pptx.shapes.group import GroupShape

from app.services.filetypes import ALLOWED, FileType

log = logging.getLogger(__name__)

# A page with fewer characters than this (ignoring whitespace) has no real text
# layer: a scan, a photo or a picture-only slide. A later vision step reads those.
SCANNED_BELOW_CHARS = 20
# Documents without page breaks (DOCX, MD, TXT) are cut into sections of about this size.
WORDS_PER_PAGE = 800
MAX_TITLE_CHARS = 500
# PDFium's error code for a missing or wrong password.
_PDF_PASSWORD_ERROR = 4

_TYPE_BY_CONTENT_TYPE: dict[str, FileType] = {a.content_type: a.type for a in ALLOWED.values()}


class ExtractionError(Exception):
    """The file can't be read. The message is safe to show, and retrying won't help."""


@dataclass(frozen=True)
class Page:
    number: int
    text: str
    title: str | None = None

    @property
    def char_count(self) -> int:
        return len(self.text)

    @property
    def is_scanned(self) -> bool:
        return len(re.sub(r"\s", "", self.text)) < SCANNED_BELOW_CHARS


def extract(content_type: str, path: Path) -> list[Page]:
    """The file's pages, numbered from 1. Raises ExtractionError."""
    kind = _TYPE_BY_CONTENT_TYPE.get(content_type)
    readers: dict[FileType, Callable[[Path], list[Page]]] = {
        "pdf": _pdf,
        "pptx": _pptx,
        "docx": _docx,
        "md": _markdown,
        "txt": _plain_text,
        "png": _image,
        "jpg": _image,
    }
    if kind is None:
        raise ExtractionError("This kind of file can't be read.")
    try:
        return readers[kind](path)
    except ExtractionError:
        raise
    except Exception as exc:
        # Library errors for broken files vary (zip, XML, KeyError…); none should leak.
        log.warning("Extraction failed for a %s file: %r", kind, exc)
        raise ExtractionError(
            f"The {kind.upper()} file couldn't be read. It may be damaged; try saving it again "
            "and re-uploading."
        ) from exc


def clean(text: str) -> str:
    """Normalise line endings and spacing; drop characters Postgres can't store."""
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _title(text: str | None) -> str | None:
    if not text:
        return None
    title = " ".join(text.split())
    return title[:MAX_TITLE_CHARS] or None


# --- PDF -----------------------------------------------------------------------------


def _pdf(path: Path) -> list[Page]:
    try:
        document = pdfium.PdfDocument(path)
    except pdfium.PdfiumError as exc:
        if getattr(exc, "err_code", None) == _PDF_PASSWORD_ERROR:
            raise ExtractionError(
                "The PDF is password-protected. Remove the password and upload it again."
            ) from exc
        raise ExtractionError(
            "The PDF couldn't be opened. It may be damaged; try saving it again and re-uploading."
        ) from exc
    try:
        pages = []
        for index in range(len(document)):
            page = document[index]
            textpage = page.get_textpage()
            try:
                pages.append(Page(index + 1, clean(textpage.get_text_range())))
            finally:
                textpage.close()
                page.close()
        return pages
    finally:
        document.close()


# --- PPTX ----------------------------------------------------------------------------


def _shape_texts(shapes: Iterable[BaseShape]) -> Iterator[str]:
    for shape in shapes:
        if isinstance(shape, GroupShape):
            yield from _shape_texts(shape.shapes)
        elif isinstance(shape, Shape) and shape.has_text_frame:
            yield shape.text_frame.text
        elif isinstance(shape, GraphicFrame) and shape.has_table:
            for row in shape.table.rows:
                yield " | ".join(cell.text for cell in row.cells)


def _pptx(path: Path) -> list[Page]:
    try:
        deck = Presentation(str(path))
    except (PptxPackageError, zipfile.BadZipFile, KeyError) as exc:
        raise ExtractionError(
            "The PPTX file couldn't be opened. It may be damaged or password-protected."
        ) from exc
    pages = []
    for number, slide in enumerate(deck.slides, start=1):
        title_shape = slide.shapes.title
        title = title_shape.text if title_shape is not None and title_shape.has_text_frame else None
        body = [
            text
            for shape_text in _shape_texts(
                # Compare ids: python-pptx hands out a new proxy object on every access.
                s
                for s in slide.shapes
                if title_shape is None or s.shape_id != title_shape.shape_id
            )
            if (text := shape_text.strip())
        ]
        notes = ""
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
            notes = slide.notes_slide.notes_text_frame.text.strip()
        parts = [part for part in (title, "\n".join(body)) if part]
        if notes:
            parts.append(f"Speaker notes:\n{notes}")
        pages.append(Page(number, clean("\n\n".join(parts)), _title(title)))
    return pages


# --- Documents without pages: DOCX, MD, TXT ----------------------------------------


@dataclass(frozen=True)
class Block:
    text: str
    heading: bool = False


def paginate(blocks: Iterable[Block], words_per_page: int = WORDS_PER_PAGE) -> list[Page]:
    """Group blocks into pages: a heading starts a new page, and so does reaching
    ``words_per_page`` (at a block boundary, never mid-paragraph)."""
    pages: list[tuple[str | None, list[str]]] = []
    title: str | None = None
    current: list[str] = []
    words = 0

    def flush() -> None:
        nonlocal current, words, title
        if current:
            pages.append((title, current))
        current, words, title = [], 0, None

    for block in blocks:
        text = block.text.strip()
        if not text:
            continue
        count = len(text.split())
        if block.heading or (current and words + count > words_per_page):
            flush()
        if block.heading:
            title = text
        current.append(text)
        words += count
    flush()
    return [
        Page(number, clean("\n\n".join(parts)), _title(page_title))
        for number, (page_title, parts) in enumerate(pages, start=1)
    ]


def _docx_blocks(path: Path) -> Iterator[Block]:
    document = Document(str(path))
    for item in document.iter_inner_content():
        if isinstance(item, Paragraph):
            style = (item.style.name if item.style is not None else "") or ""
            heading = style.startswith("Heading") or style == "Title"
            yield Block(item.text, heading=heading)
        elif isinstance(item, Table):
            rows = (" | ".join(cell.text.strip() for cell in row.cells) for row in item.rows)
            yield Block("\n".join(rows))


def _docx(path: Path) -> list[Page]:
    try:
        blocks = list(_docx_blocks(path))
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise ExtractionError(
            "The DOCX file couldn't be opened. It may be damaged or password-protected."
        ) from exc
    return paginate(blocks) or [Page(1, "")]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")  # checked as UTF-8 at upload


_MD_HEADING = re.compile(r"^#{1,6}\s")


def _markdown(path: Path) -> list[Page]:
    blocks = []
    for part in re.split(r"\n\s*\n", _read_text(path)):
        # A heading line starts its own block, even without a blank line after it.
        lines = part.strip("\n").split("\n")
        if lines and _MD_HEADING.match(lines[0]):
            blocks.append(Block(lines[0].lstrip("#").strip(), heading=True))
            lines = lines[1:]
        blocks.append(Block("\n".join(lines)))
    return paginate(blocks) or [Page(1, "")]


def _plain_text(path: Path) -> list[Page]:
    blocks = [Block(part) for part in re.split(r"\n\s*\n", _read_text(path))]
    return paginate(blocks) or [Page(1, "")]


def _image(path: Path) -> list[Page]:
    return [Page(1, "")]
