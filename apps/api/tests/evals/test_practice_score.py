"""The practice eval's scoring (evals/practice): numbers from a marked spot-check sheet."""

import csv
from pathlib import Path

from evals.practice.__main__ import COLUMNS, newest_marked, score_sheet


def row(kind: str, mark: str) -> dict[str, str]:
    return {"kind": kind, "answerable": mark}


def test_scores_marked_rows_overall_and_by_kind() -> None:
    rows = (
        [row("flashcard", "y")] * 18 + [row("flashcard", "N")] + [row("short_answer", "yes")] * 12
    )
    rows += [row("short_answer", "")]  # not marked yet
    counts = {"returned": 40, "dropped": {"not_grounded": 2, "duplicate": 1}}
    result = score_sheet(rows, counts)
    assert result["items"] == 32 and result["marked"] == 31
    assert result["grounded_pct"] == 95.0
    assert result["answerable_pct"] == round(100 * 30 / 31, 1)
    assert result["answerable_pct_by_kind"] == {
        "flashcard": round(100 * 18 / 19, 1),
        "short_answer": 100.0,
    }
    assert result["passed"] is True


def test_too_few_marks_or_too_many_noes_fail() -> None:
    assert score_sheet([row("flashcard", "y")] * 29, {"returned": 29})["passed"] is False
    rows = [row("flashcard", "y")] * 26 + [row("flashcard", "n")] * 4
    assert score_sheet(rows, {})["passed"] is False  # 86.7 %
    assert score_sheet([row("flashcard", "")], {})["answerable_pct"] is None


def test_the_newest_marked_sheet_is_read(tmp_path: Path) -> None:
    def sheet(name: str, mark: str) -> None:
        with (tmp_path / name).open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerow({c: "" for c in COLUMNS} | {"kind": "flashcard", "answerable": mark})

    sheet("spotcheck-2026-11-20-0900.csv", "y")
    sheet("spotcheck-2026-11-21-0900.csv", "")  # newer, not marked
    found = newest_marked(tmp_path)
    assert found is not None and found.name == "spotcheck-2026-11-20-0900.csv"
