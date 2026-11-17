"""Find one material's topics with the AI and store them as its proposal (ADRs 0006, 0007).

Queued when an eligible material is indexed, from "Build topic map", from the Materials
tab's retry, and once by migration 0011. Re-running replaces the material's proposal.
When the module's last pending extraction ends, the merge is queued.

Cost is bounded per run (one job, across its retries and reschedules):
- at most ``TOPIC_MAX_CALLS`` provider calls, counted from ``ai_usage.job_id``, and at most
  one repair;
- a long material is split into parts of about ``TOPIC_PART_PAGES`` pages (fewer, bigger
  parts when it's very long, so it fits with a call to spare). Each finished part is saved
  in the job's payload, so a retry doesn't pay for it again;
- a part whose reply is cut off at the output limit is split in half, budget permitting.

The material's text reaches the AI only through ``app.ai.sources``, which refuses a
material with ``allow_ai`` off; the calls use the ``long`` role (whole documents).
"""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, update

from app.ai.client import AIResult, CallBudget, get_llm_client
from app.ai.errors import AICallLimitReached, AIInvalidOutput, AITruncated
from app.ai.sources import SourcePage, material_pages_for_prompt
from app.ai.usage import job_calls
from app.core.config import get_settings
from app.jobs.context import JobContext, JobError
from app.jobs.tasks.extract_text import job_material
from app.models import Job, TopicProposal
from app.schemas.topic_maps import MaterialTopics, ProposedSubtopic
from app.services.errors import Invalid
from app.services.topic_maps import is_eligible, queue_merge_when_done
from app.services.topic_maps.combine import combine_parts
from app.services.topic_maps.prompts import Part, extraction_messages, plan_parts

INVALID = "The AI's topic list for this material didn't come out in the expected shape."
TRUNCATED = (
    "The AI's answer for this material was cut off, even for a small part of it. "
    "Try Retry later, or split the file."
)
LIMIT = (
    "Stopped after {limit} AI calls for this material without a usable answer. "
    "Use Retry on the Materials tab to try again."
)
# Below this many pages a cut-off part isn't split again.
MIN_SPLIT_PAGES = 4


def _module_id(ctx: JobContext) -> uuid.UUID:
    return uuid.UUID(str(ctx.job.payload["module_id"]))


def keep_real_pages(topics: MaterialTopics, page_numbers: set[int]) -> MaterialTopics:
    """Drop cited page numbers the material doesn't have (and duplicates), keeping order."""

    def clean(node: ProposedSubtopic) -> list[int]:
        return list(dict.fromkeys(n for n in node.pages if n in page_numbers))

    return MaterialTopics.model_validate(
        {
            "topics": [
                {
                    **topic.model_dump(),
                    "pages": clean(topic),
                    "subtopics": [
                        {**sub.model_dump(), "pages": clean(sub)} for sub in topic.subtopics
                    ],
                }
                for topic in topics.topics
            ]
        }
    )


class _Extraction:
    """One run's calls for one material, all charged to one ``CallBudget``."""

    def __init__(
        self, title: str, kind: str, total_pages: int, user_id: uuid.UUID, budget: CallBudget
    ) -> None:
        self.title, self.kind, self.total_pages = title, kind, total_pages
        self.user_id = user_id
        self.budget = budget
        self.models: list[str] = []

    async def part(self, pages: Sequence[SourcePage], number: int, of: int) -> MaterialTopics:
        messages = extraction_messages(
            self.title,
            self.kind,
            pages,
            max_chars=get_settings().topic_max_chars,
            part=Part(number, of, self.total_pages),
        )
        try:
            result: AIResult[MaterialTopics] = await get_llm_client().complete_json_result(
                "long",
                messages,
                MaterialTopics,
                purpose="topic_extraction",
                user_id=self.user_id,
                budget=self.budget,
            )
        except AITruncated as exc:
            if len(pages) < MIN_SPLIT_PAGES or self.budget.remaining < 2:
                raise JobError(TRUNCATED, retry=False) from exc
            half = len(pages) // 2
            first = await self.part(pages[:half], number, of)
            second = await self.part(pages[half:], number, of)
            return combine_parts([first, second])
        except AICallLimitReached as exc:
            raise JobError(LIMIT.format(limit=self.budget.limit), retry=False) from exc
        except AIInvalidOutput as exc:
            if self.budget.remaining == 0:
                raise JobError(INVALID, retry=False) from exc
            raise JobError(INVALID) from exc  # a retry gets a fresh call, within the budget
        self.models.append(result.route.key)
        return result.value


async def _save_progress(ctx: JobContext, done: dict[str, Any]) -> None:
    """Keep finished parts in the job's payload, committed now, so a retry skips them."""
    payload = {**ctx.job.payload, "parts": done}
    await ctx.session.execute(update(Job).where(Job.id == ctx.job.id).values(payload=payload))
    await ctx.session.commit()


async def run(ctx: JobContext) -> None:
    material = await job_material(ctx)
    user_id = ctx.job.user_id
    if material is None or not is_eligible(material):
        # Deleted, AI turned off, or a kind we don't map: nothing to send.
        await _finish(ctx)
        return
    material_id, kind = material.id, material.kind
    try:
        title, pages = await material_pages_for_prompt(ctx.session, material_id, user_id=user_id)
    except Invalid:
        await _finish(ctx)
        return
    settings = get_settings()
    calls, invalid = await job_calls(ctx.session, ctx.job.id, user_id=user_id)
    await ctx.session.commit()  # don't hold a transaction open during the AI calls

    budget = CallBudget(
        limit=settings.topic_max_calls,
        job_id=ctx.job.id,
        used=calls,
        repairs_used=min(invalid, 1),
    )
    extraction = _Extraction(title, kind, len(pages), user_id, budget)
    parts = plan_parts(
        pages, part_pages=settings.topic_part_pages, max_parts=settings.topic_max_calls - 1
    )
    done: dict[str, Any] = dict(ctx.job.payload.get("parts") or {})
    results: list[MaterialTopics] = []
    for number, part in enumerate(parts, start=1):
        key = f"{part[0].page_number}-{part[-1].page_number}" if part else "empty"
        if key in done:
            results.append(MaterialTopics.model_validate(done[key]["topics"]))
            extraction.models.append(done[key]["model"])
            continue
        topics = await extraction.part(part, number, len(parts))
        results.append(topics)
        done[key] = {"model": extraction.models[-1], "topics": topics.model_dump(mode="json")}
        if len(parts) > 1:
            await _save_progress(ctx, done)

    material = await job_material(ctx)
    if material is None or not is_eligible(material):
        await _finish(ctx)  # removed or switched off while the AI was answering
        return
    topics = keep_real_pages(combine_parts(results), {page.page_number for page in pages})
    # The model that answered most of it.
    model_key = max(set(extraction.models), key=extraction.models.count)
    provider, _, model = model_key.partition("/")
    await ctx.session.execute(
        delete(TopicProposal).where(
            TopicProposal.user_id == user_id, TopicProposal.material_id == material.id
        )
    )
    ctx.session.add(
        TopicProposal(
            user_id=user_id,
            module_id=material.module_id,
            material_id=material.id,
            provider=provider,
            model=model,
            topics=topics.model_dump(mode="json"),
        )
    )
    await _finish(ctx)


async def _finish(ctx: JobContext) -> None:
    await queue_merge_when_done(
        ctx.session, _module_id(ctx), user_id=ctx.job.user_id, finished_job=ctx.job.id
    )
    await ctx.session.commit()


async def on_failure(ctx: JobContext, message: str, *, retrying: bool) -> None:
    """A material that can't be analysed mustn't stop the module's map: merge without it."""
    if not retrying:
        await _finish(ctx)
