"""The workload estimate: 3 minutes a slide, 6 a page of text, rounded up to 5."""

from app.services.planning.workload import Workload, estimate_minutes, workload


def test_slides_and_text_pages_have_their_own_rates() -> None:
    assert estimate_minutes(10, 0) == 30
    assert estimate_minutes(0, 10) == 60
    assert estimate_minutes(18, 0) == 55  # 54, rounded up to 5
    assert estimate_minutes(1, 1) == 10  # 9 → 10


def test_no_pages_means_no_estimate() -> None:
    assert estimate_minutes(0, 0) is None
    assert workload(None, 0, 0) == Workload(None, "none", 0, 0)


def test_the_students_figure_wins_and_is_labelled_theirs() -> None:
    assert workload(90, 18, 2) == Workload(90, "yours", 18, 2)
    assert workload(None, 18, 2) == Workload(70, "estimated", 18, 2)
