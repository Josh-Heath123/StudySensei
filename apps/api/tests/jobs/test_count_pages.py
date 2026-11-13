"""Page counts for each allowed type."""

from pathlib import Path

import pytest

from app.jobs.context import JobError
from app.jobs.tasks.count_pages import page_count
from app.services.filetypes import ALLOWED
from tests.materials import samples


def written(tmp_path: Path, data: bytes) -> Path:
    path = tmp_path / "blob"
    path.write_bytes(data)
    return path


@pytest.mark.parametrize(
    ("extension", "data", "pages"),
    [
        (".pdf", samples.pdf(3), 3),
        (".pptx", samples.pptx(4), 4),  # slide rels and presentation.xml don't count
        (".docx", samples.docx(7), 7),
        (".docx", samples.docx(None), None),  # no docProps/app.xml: unknown
        (".png", samples.PNG, 1),
        (".jpg", samples.JPG, 1),
        (".txt", samples.TXT, None),
        (".md", samples.MD, None),
    ],
)
def test_page_count(tmp_path: Path, extension: str, data: bytes, pages: int | None) -> None:
    content_type = ALLOWED[extension].content_type
    assert page_count(content_type, written(tmp_path, data)) == pages


def test_a_damaged_pdf_is_a_readable_error(tmp_path: Path) -> None:
    with pytest.raises(JobError, match="damaged or password-protected"):
        page_count("application/pdf", written(tmp_path, b"%PDF-1.7\nnot really a pdf"))
