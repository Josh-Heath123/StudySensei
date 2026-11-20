"""The study-method rules table (decision 0018): every row, and first match wins."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.services.planning.methods import RULES, BlockFacts, block_facts, choose
from app.services.planning.planner import Block, BlockKind


@pytest.mark.parametrize(
    ("kind", "first", "confidence", "method"),
    [
        # Row 1: a review, whatever else is true.
        ("review", False, None, "mixed_review"),
        ("review", True, 5, "mixed_review"),
        # Row 2: a topic's first block, rated 1-2 or not rated.
        ("study", True, None, "first_pass"),
        ("study", True, 1, "first_pass"),
        ("study", True, 2, "first_pass"),
        # Row 3: a topic's first block, rated 3-5.
        ("study", True, 3, "active_recall"),
        ("study", True, 4, "active_recall"),
        ("study", True, 5, "active_recall"),
        # Row 4: spacing and later blocks, at any confidence.
        ("study", False, None, "practice"),
        ("study", False, 1, "practice"),
        ("study", False, 5, "practice"),
    ],
)
def test_each_row_of_the_table(
    kind: BlockKind, first: bool, confidence: int | None, method: str
) -> None:
    assert choose(BlockFacts(kind, first, confidence)).method == method


def test_the_table_is_four_rows_with_the_agreed_texts() -> None:
    assert [(r.method, r.text) for r in RULES] == [
        ("mixed_review", "Mixed recall across the assessment's topics, then fix the gaps."),
        ("first_pass", "Read the linked pages and make short notes."),
        ("active_recall", "Write what you remember, then check the pages."),
        ("practice", "Quiz yourself first (Quiz me), then re-read what you missed."),
    ]
    # The last row catches everything, so every block gets a method.
    assert RULES[-1].applies(BlockFacts("review", True, 1))


def test_first_match_wins() -> None:
    # A review that's also "first" with low confidence still gets the review row.
    facts = BlockFacts("review", True, 1)
    assert sum(rule.applies(facts) for rule in RULES) > 1
    assert choose(facts) is RULES[0]


def test_first_means_first_in_time_per_topic() -> None:
    start = datetime(2026, 11, 23, 16, 0, tzinfo=UTC)
    a, b = UUID(int=1), UUID(int=2)

    def block(hours: int, topic: UUID | None) -> Block:
        at = start + timedelta(hours=hours)
        return Block(
            at,
            at + timedelta(minutes=50),
            UUID(int=9),
            UUID(int=8),
            topic,
            "study" if topic else "review",
            "workload" if topic else "final_review",
        )

    blocks = [block(0, a), block(1, b), block(24, a), block(25, None), block(48, b)]
    confidence = {a: 4, b: None}
    facts = block_facts(blocks, confidence.get)

    assert [f.first_for_topic for f in facts] == [True, True, False, False, False]
    assert [choose(f).method for f in facts] == [
        "active_recall",
        "first_pass",
        "practice",
        "mixed_review",
        "practice",
    ]
