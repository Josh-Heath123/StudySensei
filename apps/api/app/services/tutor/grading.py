"""Grading a 'Quiz me' quiz: code, never a model. Its own module so that mastery (which counts
quiz answers) and the quiz service (which asks mastery for a band, ADR 0031) don't import each
other."""

from collections.abc import Sequence

from app.schemas.tutor import Quiz


def grade(quiz: Quiz, answers: Sequence[int | None]) -> list[bool | None]:
    """Per question: right, wrong, or None (not answered). Deterministic: code, never a model."""
    return [
        None if index >= len(answers) or answers[index] is None else answers[index] == q.correct
        for index, q in enumerate(quiz.questions)
    ]
