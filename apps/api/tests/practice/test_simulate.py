"""``python -m app.practice.simulate``: in memory, deterministic for a seed."""

import io

from app.practice.simulate import main, simulate


def test_the_same_seed_gives_the_same_days() -> None:
    first = simulate(5, seed=3, new_per_day=10, retention=0.9)
    assert first == simulate(5, seed=3, new_per_day=10, retention=0.9)
    assert [d.new for d in first] == [10] * 5
    assert first[0].due_cards == 0 and all(d.reviews >= d.new for d in first)
    assert all(d.left_due == 0 for d in first)


def test_no_new_items_means_no_reviews() -> None:
    assert all(d.reviews == 0 for d in simulate(3, seed=1, new_per_day=0, retention=0.9))


def test_it_prints_a_table() -> None:
    out = io.StringIO()
    assert main(["--days", "2", "--seed", "1"], out) == 0
    assert "| Day | New | Reviews | Due cards | Left due | Minutes |" in out.getvalue()
