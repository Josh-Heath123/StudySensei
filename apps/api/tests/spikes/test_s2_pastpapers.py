"""Spike S2's scoring, cutting and privacy helpers, and the answer key's own checks.

Synthetic text only: no course material."""

import io

import pytest
from PIL import Image as PILImage
from pydantic import ValidationError

from spikes.s2_pastpapers.key import Box, check_key, load_key, parse_key
from spikes.s2_pastpapers.metrics import (
    Classified,
    KeyPart,
    Predicted,
    jaccard,
    label_found,
    marks_found,
    normalise,
    qualify,
    score_classification,
    score_segmentation,
)
from spikes.s2_pastpapers.privacy import is_submission, mask_png, redact_text
from spikes.s2_pastpapers.schemas import PartClassification, SegmentedPart
from spikes.s2_pastpapers.text import Anchor, cut_parts, needs_transcription


def part(number: str, marks: float, page: int = 1, **kw: object) -> KeyPart:
    defaults: dict[str, object] = {"type": "recall", "chapter": "Ch1", "subtopics": ("A",)}
    defaults.update(kw)
    return KeyPart(number, marks, page, **defaults)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.1(a)", "1.1.a"),
        ("1.1a", "1.1.a"),
        ("Q1.1 (a)", "1.1.a"),
        ("Question 3", "3"),
        ("1a.ii", "1.a.ii"),
        ("1(a)(ii)", "1.a.ii"),
        ("2 b", "2.b"),
    ],
)
def test_numbers_are_compared_normalised(raw: str, expected: str) -> None:
    assert normalise(raw) == expected


@pytest.mark.parametrize(
    ("number", "parent", "expected"),
    [
        ("a", "2", "2.a"),
        ("(b)", "3.3", "3.3.b"),
        ("2", "4", "4.2"),
        ("2a", "2", "2a"),  # already qualified
        ("1a.ii", "1a", "1a.ii"),
        ("3", None, "3"),
        ("3", "3", "3"),
    ],
)
def test_bare_labels_are_qualified_by_their_parent(
    number: str, parent: str | None, expected: str
) -> None:
    assert qualify(number, parent) == expected


def test_segmentation_counts_number_and_marks() -> None:
    key = [part("1a", 5), part("1b", 5, page=2), part("2", 10, page=2)]
    predicted = [
        Predicted("1(a)", 5, 1),  # exact
        Predicted("1b", 4, 2),  # marks wrong
        Predicted("3", 10, 2),  # extra; "2" is missing
    ]
    score = score_segmentation(key, predicted, printed_total=20, predicted_total=20)
    assert (score.exact, score.number_only, score.missing, score.extra) == (1, 1, 1, 1)
    assert score.exact_pct == 33.3
    assert score.page_right == 2
    assert score.total_right is True
    assert score.sum_right is False  # 19 against 20
    assert score.mismatches == ["1b: marks 4 not 5", "2: missing", "3: extra"]


def test_a_duplicate_prediction_is_extra_and_no_printed_total_is_none() -> None:
    key = [part("1", 5)]
    score = score_segmentation(
        key, [Predicted("1", 5), Predicted("1", 5)], printed_total=None, predicted_total=10
    )
    assert (score.exact, score.extra, score.total_right) == (1, 1, None)


def test_jaccard() -> None:
    assert jaccard({"a", "b"}, {"a"}) == 0.5
    assert jaccard(set(), set()) == 1.0
    assert jaccard({"a"}, {"b"}) == 0.0


def test_classification_agreement() -> None:
    key = [
        part("1", 2, chapter="Ch1", subtopics=("A", "B")),
        part("2", 2, chapter="Ch2", subtopics=("C",), type="apply"),
        part("3", 2, chapter="Ch3", subtopics=(), weak=True),
        part("4", 2),  # not answered
    ]
    got = {
        "1": Classified("1", "Ch1", ("A",), "recall"),  # chapter yes, Jaccard 0.5 yes
        "2": Classified("2", "Ch1", ("C",), "explain"),  # chapter no, subtopic yes, type no
        "3": Classified("3", "Ch3", (), "recall"),  # chapter-only both sides: agrees
    }
    score = score_classification(key, got)
    assert (score.parts, score.answered) == (4, 3)
    assert (score.chapter_agree, score.subtopic_agree, score.type_agree) == (2, 3, 2)
    assert (score.strong_answered, score.strong_chapter_agree) == (2, 1)
    assert score.as_dict()["chapter_pct"] == 66.7


def test_labels_and_marks_in_a_transcription() -> None:
    text = "Question 3\na) What is a widget? (5)\nb) Name two. [2 marks]\n(ii) Why? (1 mark)"
    assert label_found(text, "3")
    assert label_found(text, "3a")
    assert label_found(text, "3.b")
    assert label_found(text, "1a.ii")
    assert not label_found(text, "3c")
    assert marks_found(text, 5)
    assert marks_found(text, 2)
    assert marks_found(text, 1)
    assert not marks_found(text, 4)


def test_cut_parts_runs_from_anchor_to_anchor_after_the_stem() -> None:
    text = (
        "Question 1 Consider a small shop with one till.\n"
        "a) Which records must the shop keep safe? (3)\n"
        "b) Who might try to read them and why? (2)\n"
        "Question 2 Explain a widget in detail. (4)"
    )
    anchors = [
        Anchor("1a", "1", "Which records must the shop keep safe?"),
        Anchor("1b", "1", "Who might try to read them"),
        Anchor("2", None, "Explain a widget in detail."),
        Anchor("3", None, "Never printed anywhere at all"),
    ]
    cuts = cut_parts(text, anchors)
    assert [c.found for c in cuts] == [True, True, True, False]
    assert "small shop" in cuts[0].text and "(3)" in cuts[0].text and "Who" not in cuts[0].text
    # The second part of a question gets the same stem.
    assert "small shop" in cuts[1].text and "Who might" in cuts[1].text
    assert cuts[2].text.startswith("Explain a widget")
    assert cuts[3].text == "Never printed anywhere at all"


def test_nearly_empty_text_layers_are_transcribed() -> None:
    assert needs_transcription(True, 5000)
    assert needs_transcription(False, 37)
    assert not needs_transcription(False, 1500)


def test_names_with_titles_and_examiner_lines_are_redacted() -> None:
    text = (
        "Examiners: Prof A. B. Someone\nInternal Examiner: Dr Jane Doe\n"
        "Suppose Prof Smith wants to share code. Ms Ndlovu agrees.\nNo names here."
    )
    out = redact_text(text)
    for name in ("Someone", "Jane", "Doe", "Smith", "Ndlovu"):
        assert name not in out
    assert "Suppose [name] wants to share code." in out
    assert out.endswith("No names here.")


def test_the_submission_pattern_matches_case_insensitively() -> None:
    assert is_submission("X12_P1.pdf", "x12_*")
    assert not is_submission("ST1 2017.pdf", "x12_*")


def test_masks_paint_boxes_white() -> None:
    image = PILImage.new("RGB", (100, 100), "black")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    out = PILImage.open(io.BytesIO(mask_png(buffer.getvalue(), (Box(0.0, 0.0, 0.5, 0.5),))))
    assert out.getpixel((10, 10)) == (255, 255, 255)
    assert out.getpixel((90, 90)) == (0, 0, 0)


def test_first_words_are_trimmed_to_12_and_topics_are_1_to_3() -> None:
    seg = SegmentedPart(number="1", marks=2, page=1, first_words=" ".join(["w"] * 15))
    assert len(seg.first_words.split()) == 12
    with pytest.raises(ValidationError):
        PartClassification(topics=[], type="recall")
    with pytest.raises(ValidationError):
        PartClassification(topics=["t1", "t2", "t3", "t4"], type="recall")


def test_the_cos330_key_sums_to_its_printed_totals() -> None:
    key = load_key("cos330")
    assert check_key(key) == []
    assert [len(p.parts) for p in key.papers] == [11, 21, 33, 23, 15]
    assert sum(p.marks_sum for p in key.papers) == 330


def test_check_key_reports_a_wrong_sum_and_an_excluded_page() -> None:
    raw = {
        "module": "X",
        "papers": [
            {
                "label": "P",
                "title": "P",
                "printed_total": 10,
                "excluded_pages": [2],
                "parts": [
                    {"number": "1", "marks": 4, "page": 1, "type": "recall", "topics": ["Ch1"]},
                    {"number": "2", "marks": 4, "page": 2, "type": "apply", "topics": ["Ch1"]},
                ],
            }
        ],
    }
    assert check_key(parse_key(raw)) == [
        "P: parts sum to 8, printed 10",
        "P 2: on an excluded page",
    ]
