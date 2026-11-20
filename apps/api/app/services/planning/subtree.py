"""Topic subtrees for planning (decision 0019). Pure: no database.

Ticking a topic in an assessment means its whole subtree. The **planning unit** is each covered
topic with no covered ancestor; covered descendants are absorbed into it. A unit's figures come
from its subtree:

- **workload:** the student's own figure on the unit, else the estimate of decision 0016 over
  the distinct pages linked to the unit or any descendant (a page linked to both a parent and a
  child counts once), else none;
- **confidence:** the unit's own rating, else the mean of its rated descendants rounded half
  up, else not rated;
- **studied minutes:** sessions on the unit or any descendant (summed by the caller).

The topic tree API's ``workload_with_subtopics`` uses ``subtree_workload`` too, so the dialog
shows the planner's figure.
"""

import math
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from app.services.planning.workload import Workload, workload

# A material page: (material id, page number, is a slide).
Page = tuple[uuid.UUID, int, bool]
ConfidenceSource = Literal["yours", "subtopics", "none"]


@dataclass(frozen=True)
class Tree:
    parent: Mapping[uuid.UUID, uuid.UUID | None]
    children: Mapping[uuid.UUID, tuple[uuid.UUID, ...]]
    # Course order: the index in a pre-order walk (a parent before its children, siblings in
    # the order given).
    order: Mapping[uuid.UUID, int]


def make_tree(topics: Sequence[tuple[uuid.UUID, uuid.UUID | None]]) -> Tree:
    """``topics`` is (id, parent id) in sibling order (position, then name). A topic whose
    parent isn't listed is a root."""
    ids = {topic_id for topic_id, _ in topics}
    parent = {t: (p if p in ids else None) for t, p in topics}
    children: dict[uuid.UUID, list[uuid.UUID]] = {t: [] for t, _ in topics}
    roots: list[uuid.UUID] = []
    for topic_id, _ in topics:
        found = parent[topic_id]
        (children[found] if found is not None else roots).append(topic_id)
    order: dict[uuid.UUID, int] = {}
    stack = list(reversed(roots))
    while stack:
        topic_id = stack.pop()
        if topic_id in order:  # a cycle can't be stored, but never loop on one
            continue
        order[topic_id] = len(order)
        stack.extend(reversed(children[topic_id]))
    return Tree(parent, {t: tuple(c) for t, c in children.items()}, order)


def descendants(tree: Tree, topic_id: uuid.UUID) -> list[uuid.UUID]:
    """Every topic under ``topic_id``, in course order (not the topic itself)."""
    out: list[uuid.UUID] = []
    stack = list(reversed(tree.children.get(topic_id, ())))
    while stack:
        found = stack.pop()
        if found in out:
            continue
        out.append(found)
        stack.extend(reversed(tree.children.get(found, ())))
    return out


def subtree(tree: Tree, topic_id: uuid.UUID) -> list[uuid.UUID]:
    """The topic and every topic under it."""
    return [topic_id, *descendants(tree, topic_id)]


def ancestors(tree: Tree, topic_id: uuid.UUID) -> list[uuid.UUID]:
    out: list[uuid.UUID] = []
    found = tree.parent.get(topic_id)
    while found is not None and found not in out:
        out.append(found)
        found = tree.parent.get(found)
    return out


def units(tree: Tree, covered: Iterable[uuid.UUID]) -> list[uuid.UUID]:
    """The covered topics with no covered ancestor, in course order. Topics not in the tree
    are ignored."""
    ticked = {t for t in covered if t in tree.order}
    return sorted(
        (t for t in ticked if not ticked.intersection(ancestors(tree, t))),
        key=lambda t: tree.order[t],
    )


@dataclass(frozen=True)
class SubtreeWorkload:
    workload: Workload
    # How many topics are under the unit.
    subtopics: int


def subtree_workload(
    tree: Tree,
    topic_id: uuid.UUID,
    override: int | None,
    pages: Mapping[uuid.UUID, set[Page]],
) -> SubtreeWorkload:
    """The unit's workload: ``override`` (the student's figure on the unit), else the estimate
    over the distinct pages linked anywhere in the subtree, else none."""
    members = subtree(tree, topic_id)
    linked: set[Page] = set()
    for member in members:
        linked |= pages.get(member, set())
    slides = sum(1 for page in linked if page[2])
    return SubtreeWorkload(workload(override, slides, len(linked) - slides), len(members) - 1)


def subtree_confidence(
    tree: Tree, topic_id: uuid.UUID, confidence: Mapping[uuid.UUID, int | None]
) -> tuple[int | None, ConfidenceSource]:
    """The unit's own rating; else the mean of its rated descendants, rounded half up; else
    not rated."""
    own = confidence.get(topic_id)
    if own is not None:
        return own, "yours"
    rated = [c for t in descendants(tree, topic_id) if (c := confidence.get(t)) is not None]
    if not rated:
        return None, "none"
    return math.floor(sum(rated) / len(rated) + 0.5), "subtopics"
