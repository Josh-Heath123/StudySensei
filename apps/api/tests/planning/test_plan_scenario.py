"""The roadmap's Verify step for Phase 4: 2 modules, exams in 10 and 20 days, 12 h a week.
Then skip a block and re-plan, and time a big plan. Run with ``-s`` to see the plans."""

import time as clock
from collections import defaultdict
from datetime import date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from app.services.planning.availability import Rule, Window, expand, parse_minute
from app.services.planning.planner import (
    AssessmentInput,
    Block,
    Plan,
    PlanInput,
    TopicInput,
    plan,
    required_minutes,
)
from tests.planning.plan_checks import check_plan, spacing_applies

TZ = ZoneInfo("Africa/Johannesburg")
NOW = datetime(2026, 11, 23, 8, 0, tzinfo=TZ)  # Monday 08:00
MODULES = {UUID(int=9001): "MOD-A", UUID(int=9002): "MOD-B"}
MOD_A, MOD_B = MODULES


def w(weekday: int, start: str, end: str) -> Rule:
    return Rule(weekday, Window(parse_minute(start), parse_minute(end)))


# 12 h a week: weekday evenings 18:00-20:00 and Saturday 09:00-11:00.
RULES = [w(d, "18:00", "20:00") for d in range(5)] + [w(5, "09:00", "11:00")]

# name, module, workload (None: no estimate), confidence
TOPICS = [
    ("A1 Access control", MOD_A, 120, 2),
    ("A2 Cryptography", MOD_A, 90, 3),
    ("A3 Network security", MOD_A, 150, 4),
    ("A4 Malware", MOD_A, None, None),
    ("B1 Scheduling", MOD_B, 180, 1),
    ("B2 Memory", MOD_B, 60, 5),
    ("B3 File systems", MOD_B, 120, None),
    ("B4 Deadlocks", MOD_B, 200, 3),
]
NAMES = {UUID(int=i + 1): name for i, (name, *_) in enumerate(TOPICS)}


def scenario(now: datetime = NOW, studied: dict[UUID, int] | None = None) -> PlanInput:
    topics = tuple(
        TopicInput(UUID(int=i + 1), module, workload, confidence)
        for i, (_, module, workload, confidence) in enumerate(TOPICS)
    )
    exam_a = NOW.replace(hour=9) + timedelta(days=10)
    exam_b = NOW.replace(hour=9) + timedelta(days=20)
    assessments = (
        AssessmentInput(
            UUID(int=101), MOD_A, exam_a, 60.0, tuple(UUID(int=i) for i in (1, 2, 3, 4))
        ),
        AssessmentInput(
            UUID(int=102), MOD_B, exam_b, 50.0, tuple(UUID(int=i) for i in (5, 6, 7, 8))
        ),
    )
    days = expand(RULES, {}, now.date(), exam_b.date(), TZ, 180)
    return PlanInput(
        now=now.astimezone(TZ),
        free=tuple(i for day in days for i in day.intervals),
        daily_cap_minutes=180,
        timezone=TZ,
        assessments=assessments,
        topics=topics,
        studied_minutes=studied or {},
    )


def describe(request: PlanInput, result: Plan, title: str) -> str:
    exams = {a.id: f"{MODULES[a.module_id]} exam" for a in request.assessments}
    lines = [f"\n=== {title} ===", f"now {request.now.astimezone(TZ):%a %d %b %H:%M}"]
    for a in request.assessments:
        lines.append(f"{exams[a.id]} due {a.due_at.astimezone(TZ):%a %d %b %H:%M}")
    day: date | None = None
    for b in result.blocks:
        start, end = b.start.astimezone(TZ), b.end.astimezone(TZ)
        if start.date() != day:
            day = start.date()
            lines.append(f"  {start:%a %d %b}")
        what = f"Review: {exams[b.assessment_id]}" if b.topic_id is None else NAMES[b.topic_id]
        lines.append(f"    {start:%H:%M}-{end:%H:%M}  {what:<24} {b.reason}")
    lines.append("  per topic: required / planned (blocks, days)")
    for topic in request.topics:
        mine = [b for b in result.blocks if b.topic_id == topic.id]
        need = required_minutes(topic, request.studied_minutes.get(topic.id, 0))
        planned = sum(b.minutes for b in mine)
        days = len({b.start.astimezone(TZ).date() for b in mine})
        lines.append(
            f"    {NAMES[topic.id]:<24} {need:>4} / {planned:>4} min ({len(mine)}, {days})"
        )
    for s in result.shortfalls:
        topic_name = NAMES[s.topic_id] if s.topic_id else exams[s.assessment_id]
        numbers = f"needs {s.required_minutes}, planned {s.scheduled_minutes} min"
        lines.append(f"  shortfall {s.kind}: {topic_name} ({numbers})")
    return "\n".join(lines)


def minutes_by_topic(blocks: list[Block] | tuple[Block, ...]) -> dict[UUID, int]:
    out: dict[UUID, int] = defaultdict(int)
    for b in blocks:
        if b.topic_id is not None:
            out[b.topic_id] += b.minutes
    return out


def test_two_modules_exams_in_10_and_20_days_12_hours_a_week() -> None:
    request = scenario()
    assert sum(d.minutes for d in request.free) // 60 >= 12 * 2  # about 3 weeks of 12 h
    result = plan(request)
    print(describe(request, result, "Scenario: 2 modules, exams in 10 and 20 days, 12 h a week"))
    check_plan(request, result)
    assert all(spacing_applies(request, result, a) for a in request.assessments)

    reviews = [b for b in result.blocks if b.kind == "review"]
    assert len(reviews) == 2
    for review in reviews:
        due = next(a.due_at for a in request.assessments if a.id == review.assessment_id)
        assert due - timedelta(days=3) <= review.start < due
    # Every topic gets two blocks on different days; exam A's all come before exam A.
    for topic in request.topics:
        mine = [b for b in result.blocks if b.topic_id == topic.id]
        assert len({b.start.astimezone(TZ).date() for b in mine}) >= 2
    exam_a = request.assessments[0]
    assert all(b.end <= exam_a.due_at for b in result.blocks if b.module_id == MOD_A)
    # A4 has no estimate: two default blocks and a shortfall saying so.
    assert [s.kind for s in result.shortfalls if s.topic_id == UUID(int=4)] == ["no_estimate"]


def test_skipping_a_block_re_places_that_topics_time() -> None:
    request = scenario()
    first = plan(request)
    study = [b for b in first.blocks if b.kind == "study"]
    skipped = study[3]
    # Everything before the skipped block was studied as planned; the skipped one wasn't.
    done = minutes_by_topic([b for b in study if b.end <= skipped.start])
    later = scenario(now=skipped.end.astimezone(TZ), studied=dict(done))
    second = plan(later)
    print(describe(later, second, f"After skipping {NAMES[skipped.topic_id or UUID(int=0)]}"))
    check_plan(later, second)

    assert skipped.topic_id is not None
    topic = next(t for t in later.topics if t.id == skipped.topic_id)
    need = required_minutes(topic, done.get(topic.id, 0))
    planned = minutes_by_topic(second.blocks)[topic.id]
    assert planned >= need
    assert not [
        s for s in second.shortfalls if s.topic_id == topic.id and s.kind == "not_enough_time"
    ]
    # The skipped block's minutes come back: what was planned after it, plus the block itself.
    before = minutes_by_topic([b for b in study if b.start > skipped.start])[topic.id]
    assert planned >= min(need, before + skipped.minutes)


def test_2_modules_30_topics_30_days_plans_in_under_200_ms() -> None:
    rules = [w(d, "09:00", "12:00") for d in range(7)] + [w(d, "14:00", "18:00") for d in range(7)]
    topics = tuple(
        TopicInput(UUID(int=i + 1), module, 30 + (i * 37) % 240, 1 + i % 5)
        for m, module in enumerate(MODULES)
        for i in range(m * 30, m * 30 + 30)
    )
    assessments = tuple(
        AssessmentInput(
            UUID(int=200 + k),
            module,
            NOW + timedelta(days=12 + 6 * k),
            float(10 * (k + 1)),
            tuple(t.id for t in topics if t.module_id == module)[half * 15 : half * 15 + 15],
        )
        for k, (module, half) in enumerate([(MOD_A, 0), (MOD_B, 0), (MOD_A, 1), (MOD_B, 1)])
    )
    days = expand(rules, {}, NOW.date(), NOW.date() + timedelta(days=30), TZ, 240)
    request = PlanInput(
        NOW,
        tuple(i for day in days for i in day.intervals),
        240,
        TZ,
        assessments,
        topics,
        {},
    )
    timings = []
    for _ in range(3):
        started = clock.perf_counter()
        result = plan(request)
        timings.append(clock.perf_counter() - started)
    check_plan(request, result)
    print(
        f"\n60 topics, 4 assessments, 30 days: {len(result.blocks)} blocks, "
        f"{len(result.shortfalls)} shortfalls; best of 3 {min(timings) * 1000:.0f} ms "
        f"(runs: {', '.join(f'{t * 1000:.0f}' for t in timings)} ms)"
    )
    assert min(timings) < 0.2
