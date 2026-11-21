"""Simulate the review load FSRS gives, in memory: no database, no course content, no AI.

    uv run python -m app.practice.simulate [--days 30] [--seed 1] [--new-per-day 20]
        [--retention 0.90]

A student with plenty of synthetic items sits down at 18:00 UTC each day and works the queue
as the app orders it: due items first, then new ones up to the daily allowance. Each review
takes 20 seconds of simulated time, so learning steps (1 and 10 minutes) come due again in
the same sitting; the sitting ends when nothing more is due (or after 3 hours). The student
answers Again, Hard, Good or Easy with fixed probabilities. It prints, per day: new items
started, reviews done (learning steps included), the started items that came due, what was
still due when the sitting ended, and the active minutes (20 s a review).

Every interval comes from ``services/practice/scheduling.py``, the code the API uses.
"""

import argparse
import random
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TextIO

from app.services.practice.scheduling import MemoryState, SchedulingSettings, schedule

START = datetime(2026, 1, 5, 18, 0, tzinfo=UTC)
SECONDS_A_REVIEW = 20
LONGEST_SITTING = timedelta(hours=3)
# Again, Hard, Good, Easy.
GRADE_ODDS = (0.10, 0.15, 0.65, 0.10)


@dataclass
class Day:
    number: int
    new: int
    reviews: int
    # Items already started (not new) that came due during the sitting.
    due_cards: int
    # Items still due when the sitting ended: the backlog carried to tomorrow.
    left_due: int
    # Active time: reviews x 20 s (waiting for a learning step isn't counted).
    minutes: float


def simulate(
    days: int, *, seed: int, new_per_day: int, retention: float, pool: int = 5000
) -> list[Day]:
    rng = random.Random(seed)
    settings = SchedulingSettings(desired_retention=retention)
    states: list[MemoryState] = []
    unseen = pool
    out: list[Day] = []
    for number in range(1, days + 1):
        start = START + timedelta(days=number - 1)
        now = start
        seen: set[int] = set()
        new_left = min(new_per_day, unseen)
        new = reviews = 0
        while now - start < LONGEST_SITTING:
            due = sorted(
                (i for i, s in enumerate(states) if s.due <= now), key=lambda i: states[i].due
            )
            if due:
                index = due[0]
                seen.add(index)
                states[index], _ = schedule(states[index], _grade(rng), now, settings)
            elif new_left > 0:
                state, _ = schedule(None, _grade(rng), now, settings)
                states.append(state)
                seen.add(len(states) - 1)
                new_left -= 1
                unseen -= 1
                new += 1
            else:
                # Wait for a learning step due later in the sitting, or stop.
                soon = [s.due for s in states if now < s.due <= start + LONGEST_SITTING]
                if not soon or min(soon) - now > timedelta(minutes=15):
                    break
                now = min(soon)
                continue
            reviews += 1
            now += timedelta(seconds=SECONDS_A_REVIEW)
        left_due = sum(1 for s in states if s.due <= now)
        minutes = reviews * SECONDS_A_REVIEW / 60
        out.append(Day(number, new, reviews, len(seen) - new, left_due, minutes))
    return out


def _grade(rng: random.Random) -> int:
    return rng.choices((1, 2, 3, 4), weights=GRADE_ODDS)[0]


def table(days: list[Day]) -> str:
    lines = [
        "| Day | New | Reviews | Due cards | Left due | Minutes |",
        "| --: | --: | ------: | --------: | -------: | ------: |",
    ]
    for day in days:
        lines.append(
            f"| {day.number} | {day.new} | {day.reviews} | {day.due_cards} | {day.left_due} | "
            f"{day.minutes:.0f} |"
        )
    total = sum(d.reviews for d in days)
    lines.append(
        f"| **Total** | {sum(d.new for d in days)} | {total} | "
        f"{sum(d.due_cards for d in days)} | | "
        f"{sum(d.minutes for d in days):.0f} |"
    )
    return "\n".join(lines)


def main(argv: list[str], out: TextIO = sys.stdout) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.practice.simulate", description=__doc__)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--new-per-day", type=int, default=20)
    parser.add_argument("--retention", type=float, default=0.9)
    args = parser.parse_args(argv)
    days = simulate(
        args.days, seed=args.seed, new_per_day=args.new_per_day, retention=args.retention
    )
    odds = ", ".join(
        f"{name} {p:.0%}"
        for name, p in zip(("again", "hard", "good", "easy"), GRADE_ODDS, strict=True)
    )
    print(
        f"{args.days} days, {args.new_per_day} new a day, retention {args.retention:.2f}, "
        f"seed {args.seed}; grades {odds}; {SECONDS_A_REVIEW} s a review (all simulated)\n",
        file=out,
    )
    print(table(days), file=out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
