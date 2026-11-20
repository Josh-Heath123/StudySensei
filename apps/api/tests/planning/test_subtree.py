"""Topic subtrees for planning (decision 0019): course order, units, and subtree figures."""

from uuid import UUID

from app.services.planning.subtree import (
    make_tree,
    subtree_confidence,
    subtree_workload,
    units,
)


def ids(*ns: int) -> list[UUID]:
    return [UUID(int=n) for n in ns]


# Ch1 (1) > 11, 12 > 121; Ch2 (2) > 21; Ch3 (3). Listed in sibling order, children anywhere.
TREE = make_tree(
    [
        (UUID(int=1), None),
        (UUID(int=2), None),
        (UUID(int=3), None),
        (UUID(int=11), UUID(int=1)),
        (UUID(int=12), UUID(int=1)),
        (UUID(int=21), UUID(int=2)),
        (UUID(int=121), UUID(int=12)),
    ]
)


def test_course_order_is_pre_order() -> None:
    by_order = sorted(TREE.order, key=lambda t: TREE.order[t])
    assert by_order == ids(1, 11, 12, 121, 2, 21, 3)


def test_units_are_ticked_topics_with_no_ticked_ancestor() -> None:
    assert units(TREE, ids(121, 1, 21, 12)) == ids(1, 21)
    assert units(TREE, ids(121)) == ids(121)
    # Unknown ids are ignored.
    assert units(TREE, ids(999, 3)) == ids(3)


def test_the_subtree_workload_counts_each_page_once() -> None:
    material = UUID(int=500)
    pages = {
        UUID(int=1): {(material, 1, True), (material, 2, True)},
        UUID(int=11): {(material, 1, True), (material, 9, False)},
        UUID(int=121): {(material, 2, True)},
        UUID(int=2): {(material, 3, True)},  # another chapter
    }
    found = subtree_workload(TREE, UUID(int=1), None, pages)
    assert (found.workload.slide_pages, found.workload.text_pages, found.subtopics) == (2, 1, 3)
    assert (found.workload.minutes, found.workload.source) == (15, "estimated")
    # The student's figure on the unit wins.
    assert subtree_workload(TREE, UUID(int=1), 300, pages).workload.minutes == 300
    assert subtree_workload(TREE, UUID(int=3), None, pages).workload.source == "none"


def test_the_subtree_confidence() -> None:
    ratings = {UUID(int=11): 1, UUID(int=12): None, UUID(int=121): 2}
    assert subtree_confidence(TREE, UUID(int=1), ratings) == (2, "subtopics")
    assert subtree_confidence(TREE, UUID(int=1), {**ratings, UUID(int=1): 4}) == (4, "yours")
    assert subtree_confidence(TREE, UUID(int=3), ratings) == (None, "none")
