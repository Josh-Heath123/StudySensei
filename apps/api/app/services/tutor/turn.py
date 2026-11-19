"""One tutor turn, without storage: build the prompt, stream the answer, report how it went.

The conversation service (``conversations.py``) stores turns; the CLI (``app/tutor/ask.py``)
runs them with ``--dry-run`` without writing anything. Both use these.

- **Prompt:** task 1's retrieval (the module's sources, the topic boost, ``allow_ai`` only)
  and templates. The last ``HISTORY_EXCHANGES`` exchanges ride along inside the same
  context budget: the sources take what they need, the history gets what's left, and the
  oldest exchange goes first. A source is never cut.
- **Answer:** ``LLMClient.stream_text`` on the smart role, interactive (ADR 0013). Errors
  become a ``failed`` result with a readable message; nothing is raised past the sources.
"""

import time
import uuid
from collections.abc import AsyncGenerator, Sequence
from contextlib import aclosing
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LLMClient, StreamDone, TextDelta
from app.ai.errors import AIRequestFailed, AIStreamFailed, AIUnavailable
from app.ai.messages import Message
from app.core.config import Settings
from app.schemas.tutor import SourceOut, SourcesEvent
from app.services.search.embedding import Embedder
from app.services.tutor.citations import parse_citations
from app.services.tutor.prompts import (
    Exchange,
    TutorMode,
    fit_history,
    history_tokens,
    tutor_messages,
)
from app.services.tutor.retrieval import PreviousSource, Source, retrieve, reuse_sources

HISTORY_EXCHANGES = 2
PURPOSE = "tutor"


@dataclass(frozen=True)
class Turn:
    question: str
    mode: TutorMode
    sources: list[Source]
    messages: list[Message]
    # Earlier exchanges that fitted (of those offered), and the estimated tokens of the
    # sources and of that history.
    history_used: int
    context_tokens: int
    history_tokens: int
    # time.monotonic() when the question arrived: timings count from here.
    started: float


@dataclass(frozen=True)
class Answer:
    """How a turn ended. ``text`` is whatever was streamed, even when it failed."""

    status: str  # complete, truncated or failed
    text: str
    model: str | None
    first_token_ms: int | None
    total_ms: int
    cited: list[str]
    unknown_citations: list[str]
    error: str | None = None
    retry_at: datetime | None = None


async def build_turn(
    session: AsyncSession,
    module_id: uuid.UUID,
    question: str,
    mode: TutorMode,
    *,
    user_id: uuid.UUID,
    topic_id: uuid.UUID | None,
    history: Sequence[Exchange],
    embedder: Embedder,
    settings: Settings,
    started: float | None = None,
    previous_question: str | None = None,
    reuse: Sequence[PreviousSource] = (),
) -> Turn:
    """Retrieve the sources and build the messages. Reads only. ``NotFound`` for a module or
    topic that isn't the user's.

    ``reuse``: the previous answer's sources, given again with their labels (the follow-up
    modes). Otherwise retrieval, with ``previous_question`` as context for a follow-up.
    """
    started = time.monotonic() if started is None else started
    budget = settings.tutor_context_max_tokens
    if reuse:
        found = await reuse_sources(session, reuse, user_id=user_id, max_tokens=budget)
    else:
        found = await retrieve(
            session,
            module_id,
            question,
            user_id=user_id,
            embedder=embedder,
            topic_id=topic_id,
            boost=settings.tutor_topic_boost,
            max_tokens=budget,
            previous_question=previous_question,
        )
    kept = fit_history(list(history)[-HISTORY_EXCHANGES:], budget - found.context_tokens)
    messages = tutor_messages(
        mode, question, [source.for_prompt() for source in found.sources], kept
    )
    return Turn(
        question=question,
        mode=mode,
        sources=found.sources,
        messages=messages,
        history_used=len(kept),
        context_tokens=found.context_tokens,
        history_tokens=history_tokens(kept),
        started=started,
    )


def sources_event(sources: Sequence[Source]) -> SourcesEvent:
    return SourcesEvent(
        sources=[
            SourceOut(
                label=s.label,
                material_id=s.material_id,
                material_title=s.material_title,
                page_number=s.page_number,
                page_title=s.page_title,
            )
            for s in sources
        ]
    )


def _ms_since(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))


async def answer(
    turn: Turn, *, client: LLMClient, user_id: uuid.UUID
) -> AsyncGenerator[SourcesEvent | TextDelta | Answer]:
    """The sources, then the answer's pieces (each naming its model), then one ``Answer``.

    If the reader stops early (the student left), the provider's stream is closed with it.
    """
    yield sources_event(turn.sources)
    parts: list[str] = []
    model: str | None = None
    first_token_ms: int | None = None
    done: StreamDone | None = None
    error: str | None = None
    retry_at: datetime | None = None
    stream = client.stream_text("smart", turn.messages, purpose=PURPOSE, user_id=user_id)
    try:
        async with aclosing(stream):
            async for item in stream:
                if isinstance(item, TextDelta):
                    if first_token_ms is None:
                        first_token_ms = _ms_since(turn.started)
                    model = item.model
                    parts.append(item.text)
                    yield item
                else:
                    done = item
    except AIUnavailable as exc:
        error, retry_at = str(exc), exc.retry_at
    except AIStreamFailed as exc:
        error, model = str(exc), exc.model
    except AIRequestFailed as exc:
        error = str(exc)
    text = "".join(parts)
    citations = parse_citations(text, [s.label for s in turn.sources])
    if done is None:
        status = "failed"
    else:
        model = done.route.key
        status = "truncated" if done.truncated else "complete"
    yield Answer(
        status=status,
        text=text,
        model=model,
        first_token_ms=first_token_ms,
        total_ms=_ms_since(turn.started),
        cited=citations.cited,
        unknown_citations=citations.unknown,
        error=error,
        retry_at=retry_at,
    )
