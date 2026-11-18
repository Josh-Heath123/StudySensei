"""Merge a module's per-material proposals into its topic tree, then link chunks (ADR 0006).

Queued when the module's last pending extract_topics job ends, and from "Build topic
map". Existing topics go in as fixed anchors; ``apply_merge`` only adds what's new.
Only proposals of materials that are still eligible (``allow_ai`` on) are sent.
"""

import asyncio
import uuid

from sqlalchemy import select

from app.ai.client import CallBudget, get_llm_client, json_instruction
from app.ai.errors import AICallLimitReached, AIInvalidOutput
from app.ai.usage import job_calls
from app.core.config import get_settings
from app.jobs.context import JobContext, JobError
from app.models import Material, Module, Topic, TopicProposal
from app.schemas.topic_maps import MaterialTopics, ModuleTopicMap
from app.services.search.embedding import get_embedder
from app.services.topic_maps import TOPIC_KINDS
from app.services.topic_maps.linking import link_module
from app.services.topic_maps.merge import apply_merge
from app.services.topic_maps.prompts import ExistingTopic, MaterialForPrompt, merge_messages

INVALID = "The AI's merged topic map didn't come out in the expected shape."
LIMIT = "Stopped after {limit} AI calls for the topic map without a usable answer."
BUSY = (
    "The AI providers were too busy to build the topic map ({count} requests turned away). "
    "Try Build topic map again later."
)


async def job_module(ctx: JobContext) -> Module | None:
    module_id = uuid.UUID(str(ctx.job.payload["module_id"]))
    return await ctx.session.scalar(
        select(Module).where(Module.id == module_id, Module.user_id == ctx.job.user_id)
    )


async def relink(ctx: JobContext, module_id: uuid.UUID) -> None:
    settings = get_settings()
    embedder = await asyncio.to_thread(get_embedder)
    await link_module(
        ctx.session,
        module_id,
        user_id=ctx.job.user_id,
        embedder=embedder,
        threshold=settings.topic_link_threshold,
        max_chunks=settings.topic_link_max_chunks,
        min_page_chars=settings.topic_link_min_page_chars,
    )


async def run(ctx: JobContext) -> None:
    module = await job_module(ctx)
    if module is None:
        return
    user_id, module_id = ctx.job.user_id, module.id
    label = f"{module.code} {module.name}"
    rows = (
        await ctx.session.execute(
            select(TopicProposal.material_id, TopicProposal.topics, Material.title, Material.kind)
            .join(
                Material,
                (Material.id == TopicProposal.material_id)
                & (Material.user_id == TopicProposal.user_id),
            )
            .where(
                TopicProposal.user_id == user_id,
                TopicProposal.module_id == module_id,
                Material.allow_ai.is_(True),
                Material.kind.in_(TOPIC_KINDS),
            )
            .order_by(Material.created_at, Material.title, Material.id)
        )
    ).all()
    materials = [
        MaterialForPrompt(material_id, title, kind, MaterialTopics.model_validate(topics))
        for material_id, topics, title, kind in rows
    ]
    existing = [
        ExistingTopic(topic_id, parent_id, name)
        for topic_id, parent_id, name in await ctx.session.execute(
            select(Topic.id, Topic.parent_id, Topic.name)
            .where(Topic.module_id == module_id, Topic.user_id == user_id)
            .order_by(Topic.position, Topic.name)
        )
    ]
    spent = await job_calls(ctx.session, ctx.job.id, user_id=user_id)
    await ctx.session.commit()  # don't hold a transaction open during the AI call
    # Bounded like an extraction (ADR 0007): fallbacks, the repair and retries all count.
    settings = get_settings()
    budget = CallBudget(
        limit=settings.topic_max_calls,
        job_id=ctx.job.id,
        used=spent.ran,
        repairs_used=min(spent.invalid, 1),
        turned_away=spent.turned_away,
        turned_away_limit=settings.topic_max_turned_away,
    )

    if materials:
        messages, refs = merge_messages(
            label,
            existing,
            materials,
            max_tokens=settings.topic_merge_max_tokens,
            overhead=json_instruction(ModuleTopicMap),
        )
        try:
            tree = await get_llm_client().complete_json(
                "long",
                messages,
                ModuleTopicMap,
                purpose="topic_merge",
                user_id=user_id,
                budget=budget,
            )
        except AICallLimitReached as exc:
            message = (
                BUSY.format(count=budget.turned_away)
                if exc.busy
                else LIMIT.format(limit=budget.limit)
            )
            raise JobError(message, retry=False) from exc
        except AIInvalidOutput as exc:
            raise JobError(INVALID, retry=budget.remaining > 0) from exc
        if await job_module(ctx) is None:
            return  # the module was deleted meanwhile
        await apply_merge(ctx.session, module_id, tree, refs, user_id=user_id)
        await ctx.session.commit()

    await relink(ctx, module_id)
    await ctx.session.commit()
