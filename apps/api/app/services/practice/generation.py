"""Writing practice items for a topic with the AI (ADR 0025).

1. ``request_generation`` (POST /topics/{id}/practice/generate): checks the topic has
   eligible sources, then adds a queued generation and its ``generate_practice`` job in one
   transaction. A partial unique index allows one queued or running generation per topic,
   so a second request is a ``Conflict`` (409), decided by Postgres.
2. The job (``jobs/tasks/generate_practice.py``): ``prepare`` gathers the sources and the
   prompts the topic already has and builds the messages; ``ask`` makes one JSON call on the
   smart role, not interactive, so it may wait out rate limits (``AIUnavailable`` with a
   ``retry_at`` reschedules the job); ``store`` filters the reply and saves, in one
   transaction, the kept items (origin ai), the sources each cites and the counts.
3. The dry run (``app/practice/generate.py``) runs ``prepare``, ``ask`` and the filter, and
   stores nothing.

AI output is stored only after ``GeneratedPractice`` validates it and the filter keeps it.
Nothing here touches the plan, timers or progress.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import CallBudget, LLMClient
from app.ai.errors import AIInvalidOutput, AIRequestFailed, AITruncated
from app.ai.messages import Message
from app.ai.routes import Route
from app.jobs.kinds import GENERATE_PRACTICE
from app.jobs.queue import enqueue
from app.models import PracticeGeneration, PracticeItem, PracticeItemSource, Topic
from app.schemas.practice import GeneratedItem, GeneratedPractice
from app.services.academics.topics import get_topic
from app.services.errors import Conflict, Invalid, NotFound
from app.services.practice.filter import Filtered, filter_items, prompt_key
from app.services.practice.prompts import MAX_EXISTING, PURPOSE, practice_messages
from app.services.practice.sources import NO_SOURCES, TopicSources, has_sources, topic_sources

BUSY = "Practice items are already being written for this topic."
INVALID = "The AI's practice items didn't come out in the expected shape, even after a repair."
TRUNCATED = "The AI's answer was cut off. Try again with fewer items."
# Provider calls one generation may use, counting fallbacks, the repair and job retries.
MAX_CALLS = 4
RECENT = 10


class GenerationFailed(Exception):
    """The AI couldn't write usable items; the message is safe to show the student."""


@dataclass(frozen=True)
class Prepared:
    topic_name: str
    count: int
    sources: TopicSources
    messages: list[Message]
    # Prompt keys the topic already has (every status): a repeat is a duplicate.
    existing_keys: frozenset[str]


@dataclass(frozen=True)
class Reply:
    items: list[GeneratedItem]
    route: Route


async def request_generation(
    session: AsyncSession, topic_id: uuid.UUID, count: int, *, user_id: uuid.UUID
) -> PracticeGeneration:
    topic = await get_topic(session, topic_id, user_id=user_id)
    if not await has_sources(session, topic, user_id=user_id):
        raise Invalid(NO_SOURCES)
    generation = PracticeGeneration(
        id=uuid.uuid4(),
        user_id=user_id,
        module_id=topic.module_id,
        topic_id=topic.id,
        status="queued",
        requested=count,
        produced=0,
        dropped={},
    )
    try:
        async with session.begin_nested():
            session.add(generation)
            await session.flush()
    except IntegrityError as exc:
        raise Conflict(BUSY) from exc
    job = enqueue(
        session, GENERATE_PRACTICE, {"generation_id": str(generation.id)}, user_id=user_id
    )
    await session.flush()
    generation.job_id = job.id
    await session.commit()
    await session.refresh(generation)
    return generation


async def recent_generations(
    session: AsyncSession, topic_id: uuid.UUID, *, user_id: uuid.UUID
) -> list[PracticeGeneration]:
    """The topic's last 10 generations, newest first."""
    await get_topic(session, topic_id, user_id=user_id)
    return list(
        await session.scalars(
            select(PracticeGeneration)
            .where(PracticeGeneration.user_id == user_id, PracticeGeneration.topic_id == topic_id)
            .order_by(PracticeGeneration.created_at.desc(), PracticeGeneration.id)
            .limit(RECENT)
        )
    )


async def existing_prompts(
    session: AsyncSession, topic_id: uuid.UUID, *, user_id: uuid.UUID
) -> tuple[list[str], set[str]]:
    """The topic's prompts, newest first (at most 30), and every prompt key it has."""
    rows = (
        await session.execute(
            select(PracticeItem.prompt, PracticeItem.prompt_key)
            .where(PracticeItem.user_id == user_id, PracticeItem.topic_id == topic_id)
            .order_by(PracticeItem.created_at.desc(), PracticeItem.id)
        )
    ).all()
    return [prompt for prompt, _ in rows[:MAX_EXISTING]], {key for _, key in rows}


async def prepare(
    session: AsyncSession, topic: Topic, count: int, *, user_id: uuid.UUID, max_tokens: int
) -> Prepared:
    """Sources, existing prompts and the messages. ``Invalid`` when there are no sources."""
    sources = await topic_sources(session, topic, user_id=user_id, max_tokens=max_tokens)
    if not sources.sources:
        raise Invalid(NO_SOURCES)
    prompts, keys = await existing_prompts(session, topic.id, user_id=user_id)
    messages = practice_messages(
        topic.name, [s.for_prompt() for s in sources.sources], count, prompts
    )
    return Prepared(topic.name, count, sources, messages, frozenset(keys))


async def ask(
    client: LLMClient,
    prepared: Prepared,
    *,
    user_id: uuid.UUID,
    budget: CallBudget | None = None,
) -> Reply:
    """One validated reply. ``GenerationFailed`` with a readable message when the model's
    reply is unusable; ``AIUnavailable`` propagates (the worker reschedules)."""
    try:
        result = await client.complete_json_result(
            "smart",
            prepared.messages,
            GeneratedPractice,
            purpose=PURPOSE,
            user_id=user_id,
            budget=budget,
            interactive=False,
        )
    except AIInvalidOutput as exc:
        raise GenerationFailed(INVALID) from exc
    except AITruncated as exc:
        raise GenerationFailed(TRUNCATED) from exc
    except AIRequestFailed as exc:
        raise GenerationFailed(str(exc)) from exc
    return Reply(result.value.items, result.route)


def keep(reply_items: Sequence[GeneratedItem], prepared: Prepared, keys: set[str]) -> Filtered:
    return filter_items(
        reply_items, labels=[s.label for s in prepared.sources.sources], existing_keys=keys
    )


async def store(
    session: AsyncSession,
    generation_id: uuid.UUID,
    prepared: Prepared,
    reply: Reply,
    *,
    user_id: uuid.UUID,
    now: datetime,
) -> PracticeGeneration | None:
    """Filter the reply against the topic's prompts as they are now, and store the kept
    items, their cited sources and the generation's counts in one transaction. None (and
    nothing stored) if the generation is gone or already finished."""
    generation = await session.scalar(
        select(PracticeGeneration)
        .where(PracticeGeneration.id == generation_id, PracticeGeneration.user_id == user_id)
        .with_for_update()
    )
    if generation is None or generation.status not in ("queued", "running"):
        return None
    _, keys = await existing_prompts(session, generation.topic_id, user_id=user_id)
    filtered = keep(reply.items, prepared, keys)
    by_label = {s.label: s for s in prepared.sources.sources}
    for generated in filtered.kept:
        item = PracticeItem(
            id=uuid.uuid4(),
            user_id=user_id,
            module_id=generation.module_id,
            topic_id=generation.topic_id,
            kind=generated.kind,
            prompt=generated.prompt,
            answer=generated.answer,
            key_points=generated.key_points if generated.kind == "short_answer" else None,
            origin="ai",
            status="active",
            provider=reply.route.provider.name,
            model=reply.route.model,
            generation_id=generation.id,
            prompt_key=prompt_key(generated.prompt),
        )
        session.add(item)
        await session.flush()
        session.add_all(
            PracticeItemSource(
                item_id=item.id,
                chunk_id=by_label[label].chunk_id,
                user_id=user_id,
                label=label,
            )
            for label in dict.fromkeys(generated.sources)
        )
    generation.status = "succeeded"
    generation.produced = len(filtered.kept)
    generation.dropped = filtered.dropped
    generation.provider = reply.route.provider.name
    generation.model = reply.route.model
    generation.error = None
    generation.finished_at = now
    await session.commit()
    return generation


async def job_generation(
    session: AsyncSession, generation_id: uuid.UUID, *, user_id: uuid.UUID
) -> tuple[PracticeGeneration, Topic]:
    row = (
        await session.execute(
            select(PracticeGeneration, Topic)
            .join(
                Topic,
                (Topic.id == PracticeGeneration.topic_id)
                & (Topic.module_id == PracticeGeneration.module_id),
            )
            .where(
                PracticeGeneration.id == generation_id,
                PracticeGeneration.user_id == user_id,
                Topic.user_id == user_id,
            )
        )
    ).first()
    if row is None:
        raise NotFound("Generation")
    return row[0], row[1]


async def mark(
    session: AsyncSession,
    generation_id: uuid.UUID,
    status: str,
    *,
    user_id: uuid.UUID,
    error: str | None = None,
    now: datetime | None = None,
) -> None:
    """Set a generation's status (and error and finish time), and commit."""
    generation = await session.scalar(
        select(PracticeGeneration).where(
            PracticeGeneration.id == generation_id, PracticeGeneration.user_id == user_id
        )
    )
    if generation is None or generation.status in ("succeeded", "failed"):
        return
    generation.status = status
    generation.error = error
    generation.finished_at = now
    await session.commit()
