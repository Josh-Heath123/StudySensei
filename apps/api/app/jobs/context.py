"""What a job handler gets, and how it reports a failure in words for people."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Job
from app.storage.base import Storage


@dataclass(frozen=True)
class JobContext:
    session: AsyncSession
    job: Job
    storage: Storage


class JobError(Exception):
    """An expected failure. Its message is safe to show the student."""


class OnFailure(Protocol):
    """Called after a failed attempt (already rolled back) to record it on the job's subject."""

    def __call__(self, ctx: JobContext, message: str, *, retrying: bool) -> Awaitable[None]: ...


@dataclass(frozen=True)
class Handler:
    run: Callable[[JobContext], Awaitable[None]]
    on_failure: OnFailure | None = None
