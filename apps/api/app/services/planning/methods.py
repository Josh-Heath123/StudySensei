"""Study methods: how to spend a block, from facts about it (decision 0018, ADR 0031).

A small rules table, kept as data: one row per rule, checked in order, first match wins. The
last row matches everything, so every block gets a method. Pure: no database, no AI.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from app.services.planning.planner import WEAK_BELOW, Block, BlockKind

Method = Literal["mixed_review", "first_pass", "active_recall", "practice"]


@dataclass(frozen=True)
class BlockFacts:
    kind: BlockKind
    # Whether this is the topic's first block in the plan (in time order).
    first_for_topic: bool
    # Self-rated 1-5, or None for not rated.
    confidence: int | None
    # Estimated mastery 0-1 (ADR 0031), or None: then the rating decides.
    mastery: float | None = None


def _weak(facts: BlockFacts) -> bool:
    """Mastery below 0.5 when it's estimated, else rated 1-2 or not rated."""
    if facts.mastery is not None:
        return facts.mastery < WEAK_BELOW
    return facts.confidence is None or facts.confidence <= 2


@dataclass(frozen=True)
class MethodRule:
    # When the rule applies, in words (for the ADR and the tests).
    when: str
    applies: Callable[[BlockFacts], bool]
    method: Method
    text: str


RULES: tuple[MethodRule, ...] = (
    MethodRule(
        "a final review",
        lambda f: f.kind == "review",
        "mixed_review",
        "Mixed recall across the assessment's topics, then fix the gaps.",
    ),
    MethodRule(
        "a topic's first block, mastery below 0.5 (else rated 1-2 or not rated)",
        lambda f: f.first_for_topic and _weak(f),
        "first_pass",
        "Read the linked pages and make short notes.",
    ),
    MethodRule(
        "a topic's first block, mastery 0.5 or more (else rated 3-5)",
        lambda f: f.first_for_topic,
        "active_recall",
        "Write what you remember, then check the pages.",
    ),
    MethodRule(
        "spacing and later blocks",
        lambda f: True,
        "practice",
        "Quiz yourself first (Quiz me), then re-read what you missed.",
    ),
)


def choose(facts: BlockFacts) -> MethodRule:
    """The first rule that applies (the last one always does)."""
    return next(rule for rule in RULES if rule.applies(facts))


def block_facts(
    blocks: Sequence[Block],
    confidence: Callable[[UUID], int | None],
    mastery: Callable[[UUID], float | None] = lambda _: None,
) -> list[BlockFacts]:
    """The facts for each block, in the order given. ``blocks`` must be sorted by start (a
    ``Plan``'s are), so "first" means first in time."""
    seen: set[UUID] = set()
    out: list[BlockFacts] = []
    for block in blocks:
        if block.topic_id is None:
            out.append(BlockFacts(block.kind, first_for_topic=False, confidence=None))
            continue
        first = block.topic_id not in seen
        seen.add(block.topic_id)
        out.append(
            BlockFacts(block.kind, first, confidence(block.topic_id), mastery(block.topic_id))
        )
    return out
