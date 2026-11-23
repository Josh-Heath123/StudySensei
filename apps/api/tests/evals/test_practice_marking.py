"""The practice marking eval's pure parts (ADR 0029): choosing items, building the three
answers with known verdicts, and scoring. No AI, no course text."""

from app.schemas.practice import verdict_for
from evals.practice_marking.__main__ import Item, cases, half, pick, score


def item(topic: str, n: int, points: int = 3) -> Item:
    return Item(topic, f"Q{n}?", f"Reference {n}.", tuple(f"Point {n}.{k}" for k in range(points)))


def test_items_come_in_turn_from_each_topic_and_need_two_key_points() -> None:
    found = pick({"A": [item("A", 1), item("A", 2, 1), item("A", 3)], "B": [item("B", 4)]}, 3)
    assert [i.prompt for i in found] == ["Q1?", "Q4?", "Q3?"]


def test_the_partly_answer_covers_the_first_half_rounded_up_which_code_calls_partly() -> None:
    for points, covered in ((2, 1), (3, 2), (4, 2), (5, 3)):
        assert half(item("A", 1, points).key_points).count("Point") == covered
        assert verdict_for(covered, points)[0] == "partly"
    assert half(("Uses a salt", "Hashes slowly.")) == "Uses a salt."


def test_three_answers_per_item_the_wrong_one_from_another_topic() -> None:
    a, b, c = item("A", 1), item("A", 2), item("B", 3)
    found = cases([a, b, c])
    assert [(x.item.prompt, x.expected) for x in found] == [
        ("Q1?", "correct"),
        ("Q1?", "partly"),
        ("Q1?", "incorrect"),
        ("Q2?", "correct"),
        ("Q2?", "partly"),
        ("Q2?", "incorrect"),
        ("Q3?", "correct"),
        ("Q3?", "partly"),
        ("Q3?", "incorrect"),
    ]
    assert found[0].answer == "Reference 1." and found[2].answer == "Reference 3."
    assert found[8].answer == "Reference 1."
    assert len(cases([a, b])) == 4  # one topic: no incorrect answers


def test_scoring_counts_agreement_overall_and_per_expected_verdict() -> None:
    found = score(
        [
            ("correct", "correct"),
            ("correct", "partly"),
            ("partly", "partly"),
            ("incorrect", "incorrect"),
            ("incorrect", None),
        ]
    )
    assert (found["cases"], found["agreed"], found["agreement_pct"], found["failed"]) == (
        5,
        3,
        60.0,
        1,
    )
    assert found["by_expected"]["correct"] == {
        "cases": 2,
        "agreed": 1,
        "agreement_pct": 50.0,
        "got": {"correct": 1, "partly": 1, "incorrect": 0, "failed": 0},
    }
    assert found["by_expected"]["incorrect"]["got"]["failed"] == 1
    assert score([])["agreement_pct"] is None
