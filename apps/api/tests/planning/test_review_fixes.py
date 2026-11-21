"""Fixes from the review of #46 (decision 0023): a re-plan after an assessment's blocks
cascaded away still writes a version, so the header's summary isn't stale."""

from datetime import timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.schemas.academics import AssessmentCreate
from app.services.academics import assessments
from app.services.planning.explain import version_summary
from app.services.planning.replan import replan
from tests.academics.conftest import forget_replans
from tests.planning.test_replan import NOW, setup


async def test_deleting_an_assessment_writes_a_version_even_if_the_blocks_are_equal(
    session: AsyncSession, user_a: User
) -> None:
    rows = await setup(session, user_a)
    # A second assessment beyond the plan's 28 days: in the report ("later"), with no blocks.
    later = await assessments.create_assessment(
        session,
        rows.module.id,
        AssessmentCreate(title="Exam", kind="exam", due_at=NOW + timedelta(days=60)),
        user_id=user_a.id,
    )
    await assessments.set_assessment_topics(session, later.id, {rows.topic.id}, user_id=user_a.id)
    await forget_replans(session, user_a)
    first = await replan(session, user_id=user_a.id, now=NOW, trigger="initial")
    assert str(later.id) in {a["assessment_id"] for a in first.report["later"]}

    await assessments.delete_assessment(session, later.id, user_id=user_a.id)
    second = await replan(
        session,
        user_id=user_a.id,
        now=NOW,
        trigger="assessment",
        detail={"assessment_id": str(later.id), "name": "COS330 Exam"},
    )

    assert second.number == 2
    # Post-merge review of #47: it no longer exists, so it was deleted, not changed.
    assert second.summary == "COS330 Exam was deleted."
    assert str(later.id) not in {a["assessment_id"] for a in second.report["later"]}



def test_a_changed_assessment_still_reads_changed() -> None:
    tz = ZoneInfo("Africa/Johannesburg")
    assert version_summary("assessment", timezone=tz, assessment="COS330 Test") == (
        "COS330 Test changed."
    )
    deleted = version_summary(
        "assessment", timezone=tz, assessment="COS330 Test", assessment_deleted=True
    )
    assert deleted == "COS330 Test was deleted."
    assert version_summary("assessment", timezone=tz, assessment_deleted=True) == (
        "An assessment was deleted."
    )
