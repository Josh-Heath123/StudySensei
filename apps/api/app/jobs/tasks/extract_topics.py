"""Find one material's topics with the AI and store them as its proposal (decision 0006).

Queued when an eligible material is indexed, from "Build topic map", and once by
migration 0011. Re-running replaces the material's proposal. When the module's last
pending extraction ends, the merge is queued.

The material's text reaches the AI only through ``app.ai.sources``, which refuses a
material with ``allow_ai`` off; the call uses the ``long`` role (whole documents).
"""

import uuid

from sqlalchemy import delete

from app.ai.client import get_llm_client
from app.ai.errors import AIInvalidOutput
from app.ai.sources import material_pages_for_prompt
from app.core.config import get_settings
from app.jobs.context import JobContext, JobError
from app.jobs.tasks.extract_text import job_material
from app.models import TopicProposal
from app.schemas.topic_maps import MaterialTopics, ProposedSubtopic
from app.services.errors import Invalid
from app.services.topic_maps import is_eligible, queue_merge_when_done
from app.services.topic_maps.prompts import extraction_messages

INVALID = "The AI's topic list for this material didn't come out in the expected shape."


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
    await ctx.session.commit()  # don't hold a transaction open during the AI call

    messages = extraction_messages(title, kind, pages, max_chars=get_settings().topic_max_chars)
    try:
        result = await get_llm_client().complete_json_result(
            "long", messages, MaterialTopics, purpose="topic_extraction", user_id=user_id
        )
    except AIInvalidOutput as exc:
        raise JobError(INVALID) from exc

    material = await job_material(ctx)
    if material is None or not is_eligible(material):
        await _finish(ctx)  # removed or switched off while the AI was answering
        return
    topics = keep_real_pages(result.value, {page.page_number for page in pages})
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
            provider=result.route.provider.name,
            model=result.route.model,
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
