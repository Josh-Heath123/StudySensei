"""The schemas S2's prompts answer in. Every reply is validated against one of these (and
repaired once by the client) before it is used; nothing here is stored by the app.

These are the starting point for Phase 6 task 3 (ADR 0032).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

QuestionType = Literal["recall", "explain", "apply", "calculate", "essay"]
MAX_FIRST_WORDS = 12


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SegmentedPart(_Strict):
    """One part of a paper that carries its own marks."""

    number: str = Field(min_length=1, max_length=24, description='As printed, e.g. "3.2" or "1a"')
    parent: str | None = Field(
        default=None, max_length=24, description="The enclosing question's number, or null"
    )
    marks: float = Field(ge=0, le=200)
    page: int = Field(ge=1, le=500, description="The page where the part starts")
    first_words: str = Field(
        max_length=200, description="The first words of the part's own text, at most 12"
    )

    @field_validator("first_words")
    @classmethod
    def _short(cls, value: str) -> str:
        words = value.split()
        # A few words over is trimmed rather than refused: they're only an anchor.
        return " ".join(words[:MAX_FIRST_WORDS])


class Segmentation(_Strict):
    """Segmentation A: a whole paper in one call."""

    total_marks: float | None = Field(
        default=None, ge=0, le=500, description="The total printed on the paper, or null"
    )
    questions: list[SegmentedPart] = Field(max_length=150)


class PageSegmentation(_Strict):
    """Segmentation B: one page, carrying over from the page before."""

    total_marks: float | None = Field(
        default=None, ge=0, le=500, description="A paper total printed on this page, or null"
    )
    questions: list[SegmentedPart] = Field(max_length=60, description="Parts that start here")
    last_number: str | None = Field(
        default=None, max_length=24, description="The last part's number on this page"
    )
    open_parent: str | None = Field(
        default=None,
        max_length=24,
        description="The question still open at the bottom of the page, or null",
    )


class ClassifiedPart(_Strict):
    number: str = Field(min_length=1, max_length=24)
    topics: list[str] = Field(min_length=1, max_length=3, description="Topic codes, best first")
    type: QuestionType


class PaperClassification(_Strict):
    """Classification C1: every part of a paper in one call."""

    questions: list[ClassifiedPart] = Field(max_length=150)


class PartClassification(_Strict):
    """Classification C2: one part, choosing from its candidate topics."""

    topics: list[str] = Field(min_length=1, max_length=3, description="Topic codes, best first")
    type: QuestionType
