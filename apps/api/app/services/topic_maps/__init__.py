"""Topic maps (decision 0006): which materials qualify, queueing the jobs, and status.

extract_topics (one per material) → merge_topics (one per module) → link_topics.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import ColumnElement, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs import queue
from app.jobs.kinds import EXTRACT_TOPICS, LINK_TOPICS, MERGE_TOPICS
from app.models import Chunk, Job, Material, TopicProposal
from app.schemas.topic_maps import TopicMapStatus
from app.services.academics.modules import get_module

# Kinds that teach a module's content. Past papers, tests and assignments are mapped
# onto topics question by question in Phase 6 instead.
TOPIC_KINDS = ("slides", "notes", "study_guide", "tutorial", "outline")
PENDING = ("queued", "running")


def is_eligible(material: Material) -> bool:
    return material.allow_ai and material.kind in TOPIC_KINDS


def _eligible(module_id: uuid.UUID, user_id: uuid.UUID) -> ColumnElement[bool]:
    return (
        (Material.module_id == module_id)
        & (Material.user_id == user_id)
        & (Material.status == "ready")
        & Material.allow_ai.is_(True)
        & Material.kind.in_(TOPIC_KINDS)
    )


def _module_jobs(kind: str, module_id: uuid.UUID, user_id: uuid.UUID) -> ColumnElement[bool]:
    return and_(
        Job.user_id == user_id,
        Job.kind == kind,
        Job.payload["module_id"].astext == str(module_id),
    )


async def _pending(
    session: AsyncSession,
    kind: str,
    module_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
    exclude: uuid.UUID | None = None,
) -> int:
    query = (
        select(func.count())
        .select_from(Job)
        .where(_module_jobs(kind, module_id, user_id), Job.status.in_(PENDING))
    )
    if exclude is not None:
        query = query.where(Job.id != exclude)
    return int(await session.scalar(query) or 0)


def queue_extraction(session: AsyncSession, material: Material) -> Job:
    return queue.enqueue(
        session,
        EXTRACT_TOPICS,
        {"material_id": str(material.id), "module_id": str(material.module_id)},
        user_id=material.user_id,
    )


async def queue_merge_when_done(
    session: AsyncSession,
    module_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
    finished_job: uuid.UUID | None = None,
) -> bool:
    """Queue the module's merge if no extraction is left pending (and none is queued).

    Called when an extract_topics job ends (succeeded, or failed for good). Doesn't commit.
    """
    if await _pending(session, EXTRACT_TOPICS, module_id, user_id=user_id, exclude=finished_job):
        return False
    if await _pending(session, MERGE_TOPICS, module_id, user_id=user_id):
        return False
    queue.enqueue(session, MERGE_TOPICS, {"module_id": str(module_id)}, user_id=user_id)
    return True


async def queue_linking(session: AsyncSession, module_id: uuid.UUID, *, user_id: uuid.UUID) -> None:
    """Queue a rebuild of the module's chunk links, unless one is already waiting.

    A module with nothing indexed has nothing to link, so nothing is queued.
    """
    indexed = await session.scalar(
        select(Chunk.id).where(Chunk.user_id == user_id, Chunk.module_id == module_id).limit(1)
    )
    if indexed is None:
        return
    waiting = await session.scalar(
        select(func.count())
        .select_from(Job)
        .where(_module_jobs(LINK_TOPICS, module_id, user_id), Job.status == "queued")
    )
    if not waiting:
        queue.enqueue(session, LINK_TOPICS, {"module_id": str(module_id)}, user_id=user_id)


async def topic_map_status(
    session: AsyncSession,
    module_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
    now: datetime | None = None,
) -> TopicMapStatus:
    await get_module(session, module_id, user_id=user_id)
    now = now or datetime.now(UTC)
    eligible = set(await session.scalars(select(Material.id).where(_eligible(module_id, user_id))))
    analysed = set(
        await session.scalars(
            select(TopicProposal.material_id).where(
                TopicProposal.user_id == user_id, TopicProposal.module_id == module_id
            )
        )
    )
    jobs = list(
        await session.scalars(
            select(Job)
            .where(
                (Job.user_id == user_id)
                & Job.kind.in_((EXTRACT_TOPICS, MERGE_TOPICS))
                & (Job.payload["module_id"].astext == str(module_id))
            )
            .order_by(Job.created_at)
        )
    )
    # The latest extraction per material decides whether it failed.
    latest: dict[str, Job] = {}
    for job in jobs:
        if job.kind == EXTRACT_TOPICS:
            latest[str(job.payload.get("material_id"))] = job
    failed_jobs = [
        job
        for material_id, job in latest.items()
        if job.status == "failed" and uuid.UUID(material_id) in eligible - analysed
    ]
    pending = [job for job in jobs if job.status in PENDING]
    resting = [
        job.run_after
        for job in pending
        if job.status == "queued"
        and job.run_after > now
        and (job.last_error or "").startswith("AIUnavailable")
    ]
    merges = [job for job in jobs if job.kind == MERGE_TOPICS and job.status == "succeeded"]
    errors = sorted(
        (job for job in jobs if job.status == "failed" and job.last_error),
        key=lambda job: job.finished_at or job.updated_at,
    )
    return TopicMapStatus(
        eligible=len(eligible),
        analysed=len(eligible & analysed),
        pending=sum(job.kind == EXTRACT_TOPICS for job in pending),
        failed=len(failed_jobs),
        merging=any(job.kind == MERGE_TOPICS for job in pending),
        waiting_until=min(resting) if resting else None,
        last_error=readable(errors[-1].last_error) if errors else None,
        merged_at=max((job.finished_at for job in merges if job.finished_at), default=None),
    )


def readable(error: str | None) -> str | None:
    """A job's stored error ("JobError: message") as the message alone."""
    if error is None:
        return None
    kind, sep, message = error.partition(": ")
    return message if sep and kind.isidentifier() else error


async def build_topic_map(
    session: AsyncSession, module_id: uuid.UUID, *, user_id: uuid.UUID
) -> TopicMapStatus:
    """Analyse every eligible material that has no proposal yet, then merge.

    Materials already analysed aren't sent again (that would spend AI quota for the same
    answer). With nothing left to analyse, the merge is queued straight away.
    """
    await get_module(session, module_id, user_id=user_id)
    waiting = {
        str(material_id)
        for material_id in await session.scalars(
            select(Job.payload["material_id"].astext).where(
                _module_jobs(EXTRACT_TOPICS, module_id, user_id), Job.status.in_(PENDING)
            )
        )
    }
    todo = list(
        await session.scalars(
            select(Material)
            .where(
                _eligible(module_id, user_id),
                Material.id.not_in(
                    select(TopicProposal.material_id).where(TopicProposal.user_id == user_id)
                ),
            )
            .order_by(Material.created_at)
        )
    )
    queued = [queue_extraction(session, m) for m in todo if str(m.id) not in waiting]
    if not queued and not waiting:
        await queue_merge_when_done(session, module_id, user_id=user_id)
    await session.commit()
    return await topic_map_status(session, module_id, user_id=user_id)
