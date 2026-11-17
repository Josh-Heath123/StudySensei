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
    """The reply still didn't match the schema after one repair attempt (or none was allowed)."""


class AIRequestFailed(Exception):
    """A provider refused the request for a reason another model won't fix (a bad key, a
    bad request). Not retried and not passed on to fallbacks (decision 0007). The message
    names the model and carries the provider's own error text; it's safe to show."""


class AICallLimitReached(AIRequestFailed):
    """The caller's ``CallBudget`` is spent: no more provider calls for this run."""


class AITruncated(Exception):
    """The reply was cut off at the model's output limit (finish_reason "length").

    Not repaired: asking again gives the same cut. Callers send less (smaller parts)."""


NOT_CONFIGURED = (
    "AI isn't set up yet. Add GEMINI_API_KEY or GROQ_API_KEY to apps/api/.env "
    "(or set OLLAMA_MODEL), then restart the API and worker."
)
