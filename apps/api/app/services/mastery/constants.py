"""Every constant of the mastery formula (ADR 0027), together. Changing one needs a new ADR
(README.md, "Changing a constant")."""

from typing import Final

# Evidence E blends recall M (FSRS's R) and accuracy A (scored attempts).
RECALL_SHARE: Final = 0.6
ACCURACY_SHARE: Final = 0.4
# Recall M is FSRS's R this many days after ``at`` (ADR 0028): R at ``at`` itself is 1.0 for
# the first day after any review, even an Again, because py-fsrs counts whole days.
RECALL_AHEAD_DAYS: Final = 7
# k: the prior counts as this many attempts. w = n / (n + k).
PRIOR_ATTEMPTS: Final = 3
# An attempt's weight in A halves every this many days (relative to the newest attempt).
HALF_LIFE_DAYS: Final = 30.0
# Fewer attempts than this: status "not_enough" (the value is still computed).
MIN_ATTEMPTS: Final = 3
# Bands: weak below 0.5, developing from 0.5, strong from 0.8.
DEVELOPING_FROM: Final = 0.5
STRONG_FROM: Final = 0.8
# A review's score by FSRS grade: Again 0, Hard 0.5, Good 1, Easy 1.
GRADE_SCORES: Final = {1: 0.0, 2: 0.5, 3: 1.0, 4: 1.0}
# The prior with no rating at all.
UNRATED_PRIOR: Final = 0.5
# Ratings are 1 to 5; P = (c - 1) / 4.
RATING_MIN: Final = 1
RATING_MAX: Final = 5

assert RECALL_SHARE + ACCURACY_SHARE == 1.0
