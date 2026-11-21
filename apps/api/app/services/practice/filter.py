"""Which generated items are kept (ADR 0025). Pure: the model's items in, kept items and
counts by reason out. The checks run in this order, and an item is dropped for the first
it fails, so each is counted once:

- ``not_grounded``: a label it cites isn't among the sources it was given;
- ``too_short``: a prompt under 8 or an answer under 2 characters;
- ``answer_repeats_prompt``: the answer is the prompt again (ignoring case, punctuation and
  spacing);
- ``missing_key_points``: a short-answer question with no key points;
- ``duplicate``: the same ``prompt_key`` as an item the topic already has, or as one kept
  earlier in the batch.
"""

import hashlib
import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field

from app.schemas.practice import DropReason, GeneratedItem

MIN_PROMPT = 8
MIN_ANSWER = 2

_PUNCTUATION = re.compile(r"[^\w\s]")


def prompt_key(prompt: str) -> str:
    """sha256 of the prompt lower-cased, with runs of whitespace as one space."""
    return hashlib.sha256(" ".join(prompt.lower().split()).encode()).hexdigest()


def _bare(text: str) -> str:
    return " ".join(_PUNCTUATION.sub(" ", text.lower()).split())


@dataclass
class Filtered:
    kept: list[GeneratedItem] = field(default_factory=list)
    dropped: dict[str, int] = field(default_factory=dict)

    def drop(self, reason: DropReason) -> None:
        self.dropped[reason] = self.dropped.get(reason, 0) + 1


def drop_reason(
    item: GeneratedItem, labels: Collection[str], seen_keys: Collection[str]
) -> DropReason | None:
    """Why this item is dropped, or None to keep it."""
    if not set(item.sources) <= set(labels):
        return "not_grounded"
    if len(item.prompt) < MIN_PROMPT or len(item.answer) < MIN_ANSWER:
        return "too_short"
    if _bare(item.answer) == _bare(item.prompt):
        return "answer_repeats_prompt"
    if item.kind == "short_answer" and not item.key_points:
        return "missing_key_points"
    if prompt_key(item.prompt) in seen_keys:
        return "duplicate"
    return None


def filter_items(
    items: Sequence[GeneratedItem], *, labels: Collection[str], existing_keys: Collection[str]
) -> Filtered:
    """The items to keep, in order, and how many were dropped for each reason."""
    result = Filtered()
    seen = set(existing_keys)
    for item in items:
        reason = drop_reason(item, labels, seen)
        if reason is not None:
            result.drop(reason)
            continue
        seen.add(prompt_key(item.prompt))
        result.kept.append(item)
    return result
