"""Errors the LLM client raises to its callers."""

from datetime import datetime


class AIUnavailable(Exception):
    """No model in the role can answer now.

    ``retry_at`` is the earliest time one should be able to (a Retry-After, or a daily
    budget resetting). It's None when no provider is set up at all: retrying won't help
    until a key is added. The message is safe to show the student.
    """

    def __init__(self, message: str, *, retry_at: datetime | None) -> None:
        super().__init__(message)
        self.retry_at = retry_at


class AIInvalidOutput(Exception):
    """The reply still didn't match the schema after one repair attempt."""


NOT_CONFIGURED = (
    "AI isn't set up yet. Add GEMINI_API_KEY or GROQ_API_KEY to apps/api/.env "
    "(or set OLLAMA_MODEL), then restart the API and worker."
)
