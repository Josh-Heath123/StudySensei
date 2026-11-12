"""Errors raised by services. The API layer maps them to HTTP responses."""


class NotFound(Exception):
    """The row doesn't exist *or belongs to another user*.

    The two cases are deliberately indistinguishable, so callers can't
    probe for other users' IDs. Maps to 404.
    """

    def __init__(self, what: str) -> None:
        super().__init__(f"{what} not found")
        self.what = what


class Conflict(Exception):
    """The change would break a uniqueness rule (e.g. duplicate module code). Maps to 409."""


class Invalid(Exception):
    """The request is well-formed but not allowed (e.g. a topic moved under itself). Maps to 422."""
