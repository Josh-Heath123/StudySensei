"""The plan preview: load the inputs, plan, choose methods, write the text and the feasibility
report. ``build`` is the one code path from inputs to blocks with their texts and the report;
``preview`` (computed on request, never stored) and ``replan.replan`` (which stores a version,
decision 0021) both use it. No AI.
"""

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.planning import (
    AssessmentFeasibilityOut,
    FeasibilityOut,
    IssueOut,
    LaterAssessmentOut,
    LeverOut,
    OverallFeasibilityOut,
    PlanBlockOut,
    PlanPreviewOut,
    TopicFeasibilityOut,
)
from app.services.planning import explain, methods
from app.services.planning.feasibility import feasibility
from app.services.planning.inputs import DEFAULT_DAYS, PlanFacts, load_plan_data
from app.services.planning.planner import Block, PlanInput, plan


@dataclass(frozen=True)
class Built:
    preview: PlanPreviewOut
    # Each planner block with its output (texts and method), in time order.
    blocks: tuple[tuple[Block, PlanBlockOut], ...]


async def preview(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    now: datetime,
    days: int = DEFAULT_DAYS,
    use_mastery: bool = True,
) -> PlanPreviewOut:
    data = await load_plan_data(
        session, user_id=user_id, now=now, days=days, use_mastery=use_mastery
    )
    return build(data.input, data.facts, now=now, days=days).preview


def build(request: PlanInput, facts: PlanFacts, *, now: datetime, days: int) -> Built:
    """Plan ``request`` and write everything about it: pure, given the loaded inputs."""
    result = plan(request)

    def confidence(topic_id: uuid.UUID) -> int | None:
        found = facts.topics.get(topic_id)
        return found.confidence if found else None

    def mastery(topic_id: uuid.UUID) -> float | None:
        found = facts.topics.get(topic_id)
        return found.mastery if found else None

    blocks: list[tuple[Block, PlanBlockOut]] = []
    for block, block_facts in zip(
        result.blocks, methods.block_facts(result.blocks, confidence, mastery), strict=True
    ):
        rule = methods.choose(block_facts)
        module = facts.modules[block.module_id]
        blocks.append(
            (
                block,
                PlanBlockOut(
                    start=block.start,
                    end=block.end,
                    minutes=block.minutes,
                    module_id=block.module_id,
                    module_code=module.code,
                    module_colour=module.colour,
                    assessment_id=block.assessment_id,
                    assessment_title=facts.assessments[block.assessment_id].title,
                    topic_id=block.topic_id,
                    topic_name=explain.topic_name(block.topic_id, facts)
                    if block.topic_id
                    else None,
                    kind=block.kind,
                    reason=block.reason,
                    method=rule.method,
                    reason_text=explain.reason_text(block, facts),
                    method_text=rule.text,
                ),
            )
        )

    report = feasibility(result, request)

    def module_code(assessment_id: uuid.UUID) -> str:
        return facts.modules[facts.assessments[assessment_id].module_id].code

    feasibility_out = FeasibilityOut(
        overall=OverallFeasibilityOut.model_validate(
            asdict(report.overall)
            | {
                "deadline": report.last_deadline,
                "line": explain.overall_line(report, facts, days),
            }
        ),
        assessments=[
            AssessmentFeasibilityOut.model_validate(
                asdict(a.numbers)
                | {
                    "assessment_id": a.assessment_id,
                    "title": facts.assessments[a.assessment_id].title,
                    "module_code": module_code(a.assessment_id),
                    "due_at": a.due_at,
                    "line": explain.assessment_line(a, facts),
                    "planned_with": list(a.planned_with),
                    "topics": [
                        TopicFeasibilityOut(
                            topic_id=t.topic_id,
                            topic_name=explain.topic_name(t.topic_id, facts),
                            required_minutes=t.required_minutes,
                            planned_minutes=t.planned_minutes,
                            short_minutes=t.short_minutes,
                        )
                        for t in a.topics
                    ],
                    "issues": [
                        IssueOut(
                            kind=s.kind,
                            topic_id=s.topic_id,
                            text=explain.shortfall_text(s, facts),
                        )
                        for s in a.shortfalls
                    ],
                }
            )
            for a in report.assessments
        ],
        later=[
            LaterAssessmentOut(
                assessment_id=assessment_id,
                title=facts.assessments[assessment_id].title,
                module_code=module_code(assessment_id),
                due_at=facts.assessments[assessment_id].due_at,
                text=explain.later_text(assessment_id, facts, days),
            )
            for assessment_id in facts.later
        ],
        levers=[
            LeverOut(
                kind=lever.kind,
                assessment_id=lever.assessment_id,
                text=explain.lever_text(lever, facts),
            )
            for lever in report.levers
        ],
        basis=explain.BASIS,
    )
    out = PlanPreviewOut(
        generated_at=now,
        timezone=facts.timezone.key,
        days=days,
        first=facts.first,
        last=facts.last,
        daily_study_cap_minutes=facts.daily_cap_minutes,
        blocks=[block_out for _, block_out in blocks],
        feasibility=feasibility_out,
    )
    return Built(out, tuple(blocks))
