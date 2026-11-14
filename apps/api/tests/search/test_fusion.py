"""Reciprocal rank fusion and snippet highlighting (pure)."""

import pytest

from app.services.search.search import (
    HIGHLIGHT_START,
    HIGHLIGHT_STOP,
    SnippetPart,
    reciprocal_rank_fusion,
    split_highlights,
)


def test_each_item_scores_the_sum_of_one_over_k_plus_rank() -> None:
    fused = dict(reciprocal_rank_fusion([["a", "b", "c"], ["c", "a"]], k=60))
    assert fused["a"] == pytest.approx(1 / 61 + 1 / 62)
    assert fused["b"] == pytest.approx(1 / 62)
    assert fused["c"] == pytest.approx(1 / 63 + 1 / 61)


def test_items_found_by_both_rankings_beat_a_top_hit_in_one() -> None:
    fused = reciprocal_rank_fusion([["solo", "both"], ["both"]])
    assert [item for item, _ in fused] == ["both", "solo"]


def test_ties_keep_first_seen_order() -> None:
    fused = reciprocal_rank_fusion([["a"], ["b"]])
    assert [item for item, _ in fused] == ["a", "b"]


def test_empty_rankings_fuse_to_nothing() -> None:
    assert reciprocal_rank_fusion([[], []]) == []


def test_default_k_is_60() -> None:
    [(item, score)] = reciprocal_rank_fusion([["a"]])
    assert item == "a"
    assert score == pytest.approx(1 / 61)


S, E = HIGHLIGHT_START, HIGHLIGHT_STOP


@pytest.mark.parametrize(
    ("headline", "parts"),
    [
        ("plain text", [SnippetPart("plain text", False)]),
        (
            f"salt the {S}password{E} first",
            [
                SnippetPart("salt the ", False),
                SnippetPart("password", True),
                SnippetPart(" first", False),
            ],
        ),
        (f"{S}a{E}{S}b{E}", [SnippetPart("a", True), SnippetPart("b", True)]),
        (f"x {S}unclosed", [SnippetPart("x ", False), SnippetPart("unclosed", True)]),
        ("", []),
        ("<b>not markup</b>", [SnippetPart("<b>not markup</b>", False)]),
    ],
)
def test_split_highlights(headline: str, parts: list[SnippetPart]) -> None:
    assert split_highlights(headline) == parts
