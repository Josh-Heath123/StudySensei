"""The chunker: one page in, chunks that fit the model out (pure, no database)."""

import pytest

from app.services.search.chunking import chunk_page, embedding_text
from tests.fakes import FakeEmbedder

count = FakeEmbedder().count_tokens


def words(n: int, prefix: str = "w") -> str:
    return " ".join(f"{prefix}{i}" for i in range(n))


def sentences(n: int, length: int = 10, prefix: str = "s") -> str:
    """n sentences of ``length`` tokens each (the full stop counts as one)."""
    return " ".join(words(length - 1, f"{prefix}{i}x") + "." for i in range(n))


def test_empty_and_blank_pages_have_no_chunks() -> None:
    assert chunk_page("", count) == []
    assert chunk_page("  \n\n \t ", count) == []


def test_a_page_that_fits_is_one_chunk_exactly_as_written() -> None:
    page = "  Title\n\nFirst  point.\n- second point\n\n"
    assert chunk_page(page, count, max_tokens=400) == ["Title\n\nFirst  point.\n- second point"]


def test_every_chunk_fits_and_is_a_slice_of_the_page() -> None:
    page = "\n\n".join(sentences(12, prefix=f"p{n}") for n in range(8))  # 960 tokens
    chunks = chunk_page(page, count, max_tokens=400, overlap=50)
    assert len(chunks) >= 3
    for chunk in chunks:
        assert count(chunk) <= 400
        assert chunk in page
    # Nothing is lost: every sentence is in some chunk.
    for sentence in page.replace("\n\n", " ").split(". "):
        assert any(sentence.strip(" .") in chunk for chunk in chunks)


def test_long_pages_split_at_paragraphs_first() -> None:
    first, second = sentences(20, prefix="a"), sentences(20, prefix="b")  # 200 tokens each
    page = f"{first}\n\n{second}"
    assert chunk_page(page, count, max_tokens=300, overlap=0) == [first, second]


def test_paragraphs_pack_together_while_they_fit() -> None:
    paragraphs = [sentences(10, prefix=f"p{n}") for n in range(4)]  # 100 tokens each
    page = "\n\n".join(paragraphs)
    chunks = chunk_page(page, count, max_tokens=250, overlap=0)
    assert chunks == ["\n\n".join(paragraphs[:2]), "\n\n".join(paragraphs[2:])]


def test_a_long_paragraph_splits_at_sentences() -> None:
    page = sentences(50)  # 500 tokens, one paragraph, one line
    chunks = chunk_page(page, count, max_tokens=200, overlap=0)
    assert [count(chunk) for chunk in chunks] == [200, 200, 100]
    assert all(chunk.endswith(".") for chunk in chunks)


def test_slide_bullets_split_at_lines() -> None:
    page = "\n".join(f"- {words(9, f'b{n}x')}" for n in range(40))  # 40 bullets, 10 tokens each
    chunks = chunk_page(page, count, max_tokens=100, overlap=0)
    assert len(chunks) == 4
    assert all(chunk.startswith("- ") for chunk in chunks)


def test_a_sentence_too_long_for_a_chunk_splits_at_words() -> None:
    page = words(1000)
    chunks = chunk_page(page, count, max_tokens=400, overlap=0)
    assert [count(chunk) for chunk in chunks] == [400, 400, 200]


def test_chunks_overlap_by_about_50_tokens_at_a_sentence_start() -> None:
    page = sentences(80)  # 800 tokens, ten per sentence
    chunks = chunk_page(page, count, max_tokens=400, overlap=50)
    assert [count(chunk) for chunk in chunks] == [400, 400, 100]
    # Sentences 0-39, then 35-74 (five sentences, 50 tokens, repeated), then 70-79.
    assert chunks[0].endswith("s39x8.")
    assert chunks[1].startswith("s35x0 ") and chunks[1].endswith("s74x8.")
    assert chunks[2].startswith("s70x0 ") and chunks[2].endswith("s79x8.")


def test_overlap_falls_back_to_words_inside_a_long_sentence() -> None:
    page = words(900)  # no sentence boundaries at all
    chunks = chunk_page(page, count, max_tokens=400, overlap=50)
    assert chunks[1].startswith("w350 ")  # the last 50 words of the first chunk
    assert all(count(chunk) <= 400 for chunk in chunks)


def test_no_overlap_when_disabled() -> None:
    page = sentences(80)
    chunks = chunk_page(page, count, max_tokens=400, overlap=0)
    assert "".join(chunks).replace(" ", "") == page.replace(" ", "")


def test_a_single_word_longer_than_a_chunk_is_kept_whole() -> None:
    giant = "x" * 50
    long_count = lambda text: 500 if giant in text else count(text)  # noqa: E731
    assert chunk_page(f"short. {giant}", long_count, max_tokens=400) == ["short.", giant]


@pytest.mark.parametrize(
    ("material", "page_title", "expected"),
    [
        ("CH03", "User authentication", "CH03 · User authentication\n\nbody"),
        ("CH03", None, "CH03\n\nbody"),
        ("CH03", "   ", "CH03\n\nbody"),
        ("  CH03 ", " Hashing ", "CH03 · Hashing\n\nbody"),
    ],
)
def test_embedding_text_leads_with_material_and_page_titles(
    material: str, page_title: str | None, expected: str
) -> None:
    assert embedding_text(material, page_title, "body") == expected


def test_embedding_text_shortens_very_long_titles() -> None:
    text = embedding_text("M" * 500, "T" * 500, "body")
    assert text == f"{'M' * 150} · {'T' * 150}\n\nbody"
