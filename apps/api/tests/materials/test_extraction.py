"""Text extraction from the generated fixtures in tests/fixtures (no course material)."""

from pathlib import Path

import pytest

from app.services.extraction import (
    SCANNED_BELOW_CHARS,
    Block,
    ExtractionError,
    Page,
    clean,
    extract,
    paginate,
)
from app.services.filetypes import ALLOWED
from tests.materials import samples

FIXTURES = Path(__file__).parents[1] / "fixtures"
CONTENT_TYPE = {ext: allowed.content_type for ext, allowed in ALLOWED.items()}


def run(name: str) -> list[Page]:
    path = FIXTURES / name
    return extract(CONTENT_TYPE[path.suffix], path)


def written(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_pdf_pages_with_an_image_only_page_marked_scanned() -> None:
    pages = run("lecture.pdf")

    assert [p.number for p in pages] == [1, 2, 3]
    assert pages[0].text == (
        "Week 3: Layered architecture\nEach layer only calls the layer below it.\n"
        "Layers make change local but can cost performance."
    )
    assert pages[0].char_count == len(pages[0].text)
    assert [p.is_scanned for p in pages] == [False, True, False]
    assert pages[1].text == ""
    assert pages[2].text.startswith("Pipes and filters\n")


def test_a_password_protected_pdf_says_so() -> None:
    with pytest.raises(ExtractionError) as error:
        run("protected.pdf")
    assert str(error.value) == (
        "The PDF is password-protected. Remove the password and upload it again."
    )


@pytest.mark.parametrize(
    "data",
    [
        b"%PDF-1.7\nthis is not really a pdf",
        (FIXTURES / "lecture.pdf").read_bytes()[:300],  # cut off mid-file
    ],
)
def test_a_damaged_pdf_says_so(tmp_path: Path, data: bytes) -> None:
    with pytest.raises(ExtractionError, match=r"couldn't be opened. It may be damaged"):
        extract("application/pdf", written(tmp_path, "broken.pdf", data))


def test_pptx_slides_have_title_body_and_speaker_notes() -> None:
    pages = run("slides.pptx")

    assert [(p.number, p.title, p.is_scanned) for p in pages] == [
        (1, "Architectural styles", False),
        (2, "Quality attributes", False),
        (3, None, True),  # a picture and nothing else
    ]
    assert pages[0].text == (
        "Architectural styles\n\nLayered\nPipes and filters\nEvent-driven\n\n"
        "Speaker notes:\nAsk the class which style their project uses."
    )
    assert pages[1].text == "Quality attributes\n\nAvailability, modifiability, performance"


def test_a_damaged_pptx_says_so(tmp_path: Path) -> None:
    # Passes the upload check (an OOXML zip with ppt/), but isn't a real presentation.
    with pytest.raises(ExtractionError) as error:
        extract(CONTENT_TYPE[".pptx"], written(tmp_path, "fake.pptx", samples.pptx(2)))
    # The library's own error never reaches the student.
    assert str(error.value) == (
        "The PPTX file couldn't be read. It may be damaged; try saving it again and re-uploading."
    )


def test_docx_splits_at_headings_and_about_every_800_words() -> None:
    pages = run("notes.docx")

    assert [p.title for p in pages] == [
        "Week 1: Introduction",
        "Week 2: Quality attributes",
        None,  # the same section, continued after ~800 words
    ]
    assert pages[0].text == (
        "Week 1: Introduction\n\n"
        "Software architecture is the set of significant design decisions.\n\n"
        "ADR | Decision record\nQA | Quality attribute"
    )
    for page in pages[1:]:
        assert len(page.text.split()) <= 800 + 3  # plus the heading's words
        assert not page.is_scanned


def test_a_damaged_docx_says_so(tmp_path: Path) -> None:
    with pytest.raises(ExtractionError, match="DOCX file couldn't be"):
        extract(CONTENT_TYPE[".docx"], written(tmp_path, "fake.docx", samples.docx()))


def test_markdown_splits_at_headings(tmp_path: Path) -> None:
    text = "# Week 1\nIntro to the module.\n\nMore intro.\n\n## Styles\n\nLayered and pipes.\n"
    pages = extract("text/markdown", written(tmp_path, "notes.md", text.encode()))

    assert [(p.title, p.text) for p in pages] == [
        ("Week 1", "Week 1\n\nIntro to the module.\n\nMore intro."),
        ("Styles", "Styles\n\nLayered and pipes."),
    ]


def test_plain_text_is_one_page_until_it_gets_long(tmp_path: Path) -> None:
    short = extract("text/plain", written(tmp_path, "a.txt", b"\xef\xbb\xbfOne short note.\n"))
    assert [(p.number, p.text, p.title) for p in short] == [(1, "One short note.", None)]

    paragraph = " ".join(["word"] * 300)
    long = "\n\n".join([paragraph] * 4)  # 1,200 words in 300-word paragraphs
    pages = extract("text/plain", written(tmp_path, "b.txt", long.encode()))
    assert [len(p.text.split()) for p in pages] == [600, 600]


@pytest.mark.parametrize("name", ["photo.png", "photo.jpg"])
def test_an_image_is_one_scanned_page(tmp_path: Path, name: str) -> None:
    data = samples.PNG if name.endswith(".png") else samples.JPG
    content_type = CONTENT_TYPE["." + name.split(".")[1]]
    assert extract(content_type, written(tmp_path, name, data)) == [Page(1, "")]
    assert Page(1, "").is_scanned


def test_empty_documents_still_have_one_page(tmp_path: Path) -> None:
    assert extract("text/plain", written(tmp_path, "a.txt", b"\n\n  \n")) == [Page(1, "")]


def test_scanned_means_under_20_characters_ignoring_whitespace() -> None:
    assert SCANNED_BELOW_CHARS == 20
    assert Page(1, "a b c d e f g h i j k l m n o p q r s").is_scanned  # 19 letters
    assert not Page(1, "a b c d e f g h i j k l m n o p q r s t").is_scanned  # 20


def test_clean_normalises_and_drops_nul() -> None:
    assert clean("  one\r\ntwo\x00\rthree   \n\n\n\nfour  ") == "one\ntwo\nthree\n\nfour"


def test_paginate_never_splits_a_paragraph() -> None:
    blocks = [Block("a " * 500), Block("b " * 500), Block("c " * 100)]
    pages = paginate(blocks, words_per_page=800)
    assert [len(p.text.split()) for p in pages] == [500, 600]


def test_unknown_content_types_are_refused(tmp_path: Path) -> None:
    with pytest.raises(ExtractionError, match="can't be read"):
        extract("application/zip", written(tmp_path, "a.zip", b"PK"))
