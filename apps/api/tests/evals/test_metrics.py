"""The evals' metric functions on tiny synthetic data (the runners need the dev database)."""

import pytest

from evals.common import load_config
from evals.metrics import (
    ChapterCounts,
    ChapterRules,
    ChunkScore,
    LinkRule,
    compare_trees,
    first_rank,
    in_top,
    mean_reciprocal_rank,
    similarity_pages,
    top_level_names,
)

# --- search ---


def test_first_rank_is_the_first_acceptable_result() -> None:
    results = [("Notes", 3), ("Deck", 7), ("Deck", 8), ("Deck", 7)]

    assert first_rank(results, {("Deck", 7), ("Deck", 8)}) == 2
    assert first_rank(results, {("Deck", 8)}) == 3
    assert first_rank(results, {("Deck", 99)}) is None
    assert first_rank([], {("Deck", 7)}) is None


def test_mrr_counts_a_miss_as_zero() -> None:
    assert mean_reciprocal_rank([1, 2, None, 4]) == pytest.approx((1 + 0.5 + 0 + 0.25) / 4)
    assert mean_reciprocal_rank([]) == 0.0


def test_in_top_counts_ranks_at_or_above_k() -> None:
    assert in_top([1, 3, 4, None], 3) == 2


# --- chapters ---

RULES = ChapterRules.from_config(
    {
        "material_chapter": [r"^CH(\d+)$", r"^COS330 Chapter(\d+) Study Notes$"],
        "topic_chapter": r"^Ch(\d+)\b",
    }
)


@pytest.mark.parametrize(
    ("title", "chapter"),
    [
        ("CH05", 5),
        ("CH13", 13),
        ("COS330 Chapter8 Study Notes", 8),
        ("COS330 Final Study Guide", None),
        ("ST1 2016", None),
        ("CH05 extra", None),
    ],
)
def test_a_materials_chapter_comes_from_its_title(title: str, chapter: int | None) -> None:
    assert RULES.material_chapter(title) == chapter


def test_a_topics_chapter_comes_from_its_top_level_ancestor() -> None:
    tree = {
        "root": ("Ch10 Buffer Overflows", None),
        "child": ("Stack overflows", "root"),
        "grandchild": ("Canaries", "child"),
        "loose": ("Notes on exams", None),
    }

    roots = top_level_names(tree)

    assert roots == {
        "root": "Ch10 Buffer Overflows",
        "child": "Ch10 Buffer Overflows",
        "grandchild": "Ch10 Buffer Overflows",
        "loose": "Notes on exams",
    }
    assert RULES.topic_chapter(roots["grandchild"]) == 10
    assert RULES.topic_chapter("Chapter one") is None  # "Ch" must be followed by digits


def test_the_cos330_config_maps_its_titles() -> None:
    rules = ChapterRules.from_config(load_config("cos330.yaml"))

    assert rules.material_chapter("CH01") == 1
    assert rules.material_chapter("COS330 Chapter5 Study Notes") == 5
    assert rules.material_chapter("COS330 Final Study Guide") is None
    assert rules.topic_chapter("Ch5 Database and Data Center Security") == 5


def test_chapter_counts_split_same_cross_and_unknown() -> None:
    counts = ChapterCounts()
    for topic, page in [(5, 5), (5, 6), (None, 5), (5, None), (8, 8)]:
        counts.add(topic, page)

    assert (counts.same, counts.cross, counts.unknown, counts.total) == (2, 1, 2, 5)


# --- topic trees ---


def test_trees_match_by_name_ignoring_case_and_spacing() -> None:
    reference = [("Ch1 Overview", None), ("Attack  Surfaces", "Ch1 Overview"), ("Gone", None)]
    current = [("ch1 overview", None), ("attack surfaces", None), ("New", "Ch1 Overview")]

    result = compare_trees(reference, current)

    assert [name for name, _ in result.matched] == ["Ch1 Overview", "Attack  Surfaces"]
    assert result.missing == [("Gone", None)]
    assert result.extra == [("New", "Ch1 Overview")]
    assert result.moved == [("Attack  Surfaces", "Ch1 Overview", None)]


# --- linking sweep ---

CANDIDATES = [
    ChunkScore("CH05", 29, 0.85),  # cited
    ChunkScore("CH05", 30, 0.80),
    ChunkScore("CH05", 30, 0.78),  # a second chunk on the same page
    ChunkScore("CH06", 4, 0.74),
    ChunkScore("CH07", 2, 0.70),
    ChunkScore("CH08", 9, 0.60),
]
CITED = {("CH05", 29)}


def test_the_sweep_counts_pages_above_the_threshold_without_cited_ones() -> None:
    pages = similarity_pages(CANDIDATES, LinkRule(0.63, 12), cited=CITED)

    assert pages == {("CH05", 30), ("CH06", 4), ("CH07", 2)}
    assert similarity_pages(CANDIDATES, LinkRule(0.75, 12), cited=CITED) == {("CH05", 30)}


def test_cited_chunks_take_places_in_the_cap() -> None:
    # The top 3 chunks are the cited page and two on page 30.
    assert similarity_pages(CANDIDATES, LinkRule(0.63, 3), cited=CITED) == {("CH05", 30)}
    assert similarity_pages(CANDIDATES, LinkRule(0.63, 4), cited=CITED) == {
        ("CH05", 30),
        ("CH06", 4),
    }


def test_the_relative_rule_keeps_scores_near_the_best_cited_one() -> None:
    rule = LinkRule(0.63, 12, delta=0.08)

    # Best cited 0.85: keep 0.77 and up.
    assert similarity_pages(CANDIDATES, rule, cited=CITED, best_cited=0.85) == {("CH05", 30)}
    # The threshold still applies when the best cited score is low.
    assert similarity_pages(CANDIDATES, rule, cited=CITED, best_cited=0.66) == {
        ("CH05", 30),
        ("CH06", 4),
        ("CH07", 2),
    }
    # No cited pages: the threshold alone.
    assert similarity_pages(CANDIDATES, rule, best_cited=None) == {
        ("CH05", 29),
        ("CH05", 30),
        ("CH06", 4),
        ("CH07", 2),
    }


def test_rule_labels_say_what_they_do() -> None:
    assert LinkRule(0.76, 12).label == "threshold 0.76, cap 12"
    assert LinkRule(0.63, 8, 0.05).label == "threshold 0.63, cap 8, within 0.05 of best cited"
