"""How long a topic takes to study: the student's own figure, or an estimate from its pages.

The estimate is computed when it's shown, never stored, and always labelled "estimated"
(decision 0016). It counts the distinct material pages linked to the topic, by kind:

- **3 minutes a slide** (``slides``): a slide carries one idea in a few lines;
- **6 minutes a page of text** (``notes``, ``study_guide``, ``tutorial``, ``other``): a
  full page of prose, read for understanding and noted;
- past papers, tests, assignments and outlines aren't counted: they're practice or
  admin, not material to learn (practice gets its own time in Phase 5).

The total is rounded up to 5 minutes.
"""

import math
from dataclasses import dataclass
from typing import Literal

SLIDE_MINUTES = 3
TEXT_PAGE_MINUTES = 6
SLIDE_KINDS = ("slides",)
TEXT_KINDS = ("notes", "study_guide", "tutorial", "other")


@dataclass(frozen=True)
class Workload:
    """``minutes`` is null when there's neither an override nor a linked page."""

    minutes: int | None
    source: Literal["yours", "estimated", "none"]
    slide_pages: int
    text_pages: int


def estimate_minutes(slide_pages: int, text_pages: int) -> int | None:
    """Minutes to study these pages, rounded up to 5; None for no pages."""
    raw = slide_pages * SLIDE_MINUTES + text_pages * TEXT_PAGE_MINUTES
    if raw == 0:
        return None
    return math.ceil(raw / 5) * 5


def workload(override: int | None, slide_pages: int, text_pages: int) -> Workload:
    """The student's figure if they gave one, else the estimate from the pages."""
    if override is not None:
        return Workload(override, "yours", slide_pages, text_pages)
    estimate = estimate_minutes(slide_pages, text_pages)
    return Workload(estimate, "none" if estimate is None else "estimated", slide_pages, text_pages)
