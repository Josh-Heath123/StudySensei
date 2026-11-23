"""Seed synthetic demo data for the README screenshots: ``npm run screenshots`` runs this.

    DATABASE_URL=...studysensei_demo STORAGE_DIR=data/demo-materials \\
        uv run python -m scripts.demo_seed --now 2026-11-19T18:20:00+02:00

Dev only, and only against a database whose name ends in ``_demo``. Everything here is
original text written for the demo (never course material). It makes one module, two
assessments, open tasks, a week of finished study sessions, and two slide decks and a set of
notes on TCP, which go through the real pipeline (extraction, chunking, local embeddings and
indexing; no AI calls). The topic tree is inserted directly, with the pages each topic cites,
and linked to the chunks the way the app does it (cited pages plus local similarity).

The plan has three days of history before ``now`` (a Thursday evening), made through the real
re-plan code: version 1 from Monday morning, Monday's block done with a linked session,
Tuesday's skipped and Wednesday's missed; then the week's plan as of ``now``, with the block in
progress.

It also opens a study session 18 minutes before ``now``, with one tutor exchange about it: a
question and a stored answer written for the demo (no AI call), citing the demo's own pages,
then a "Quiz me" on it, so the session and quiz screenshots show the tutor panel.

Practice: synthetic cards on general TCP facts (``PRACTICE``), reviewed through the real
scheduler at past times, so one topic reads strong, one developing and one weak, with cards
due now, one in a learning step and new ones; one AI-written short answer cites a slide.
"""

import argparse
import asyncio
import io
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.jobs.kinds import EXTRACT_TOPICS, LINK_TOPICS, MERGE_TOPICS, REPLAN
from app.jobs.worker import run_once
from app.models import (
    AvailabilityException,
    AvailabilityRule,
    Chunk,
    Conversation,
    Job,
    Material,
    MaterialPage,
    Message,
    MessageSource,
    PlanBlock,
    PracticeItem,
    PracticeItemSource,
    Topic,
    TopicPage,
    User,
)
from app.schemas.academics import AssessmentCreate, ModuleCreate, TaskCreate, TopicCreate
from app.schemas.materials import MaterialKind
from app.schemas.practice import ItemCreate, ReviewIn
from app.schemas.sessions import EventBatch, ReflectionIn, SessionStart
from app.schemas.tutor import Quiz
from app.services.academics import assessments, modules, tasks, topics
from app.services.mastery.load import module_mastery
from app.services.materials import upload_material
from app.services.planning.replan import current_version, replan, skip_block
from app.services.practice import items
from app.services.practice.reviewing import review_item
from app.services.search.embedding import get_embedder
from app.services.sessions import sessions
from app.services.topic_maps.linking import link_module
from app.storage.local import get_storage
from tests.fixtures.make_fixtures import notes_docx, slide_deck_pdf

# The local user's timezone (the default in users.timezone).
TIMEZONE = "Africa/Johannesburg"

RELIABLE = [
    ("Week 5: TCP reliable transport", ["NET201 Computer Networks", "Lecture 9"]),
    (
        "Connection set-up: the three-way handshake",
        [
            "The client sends SYN with its initial sequence number",
            "The server answers SYN-ACK with its own sequence number",
            "The client's ACK completes the handshake; data can flow",
            "Random initial numbers stop old segments being accepted",
        ],
    ),
    (
        "Sequence numbers and acknowledgements",
        [
            "Each byte in the stream has a sequence number",
            "An ACK names the next byte the receiver expects",
            "ACKs are cumulative: one ACK covers every earlier byte",
            "Duplicate ACKs signal a gap in what has arrived",
        ],
    ),
    (
        "Flow control: the receive window",
        [
            "The receiver advertises how much buffer space it has left",
            "The sender keeps unacknowledged data within that window",
            "A zero window pauses the sender; probes check for space",
            "Flow control protects the receiver, not the network",
        ],
    ),
    (
        "Retransmission timeout",
        [
            "The sender times each segment it has not seen acknowledged",
            "The timeout follows a smoothed estimate of the round-trip time",
            "On a timeout the segment is sent again and the timer doubles",
            "Too short a timeout wastes capacity on needless resends",
        ],
    ),
]

CONGESTION = [
    ("Week 6: TCP congestion control", ["NET201 Computer Networks", "Lecture 11"]),
    (
        "Why congestion control?",
        [
            "Routers drop packets when their queues overflow",
            "Senders must share a bottleneck link fairly",
            "TCP infers congestion from loss and duplicate ACKs",
            "The congestion window (cwnd) limits data in flight",
        ],
    ),
    (
        "Slow start",
        [
            "A new connection starts with a small congestion window",
            "Each ACK grows cwnd by one segment, so it doubles every RTT",
            "Growth is exponential until loss or the threshold",
            "It quickly finds the available capacity of the path",
        ],
    ),
    (
        "The slow start threshold (ssthresh)",
        [
            "ssthresh marks where slow start hands over to avoidance",
            "Below the slow start threshold cwnd doubles each round trip",
            "Above it cwnd grows by about one segment per round trip",
            "After a loss ssthresh is set to half the window in flight",
        ],
    ),
    (
        "Congestion avoidance: AIMD",
        [
            "Additive increase: one segment per round trip",
            "Multiplicative decrease: halve cwnd on a loss",
            "The sawtooth shape shares bandwidth between flows",
            "AIMD converges towards a fair share of the link",
        ],
    ),
    (
        "Fast retransmit and fast recovery",
        [
            "Three duplicate ACKs suggest a single lost segment",
            "Fast retransmit resends it without waiting for the timer",
            "Fast recovery halves cwnd instead of restarting slow start",
            "A timeout still drops cwnd back to one segment",
        ],
    ),
]

NOTES = [
    (
        "Reliable transport in TCP",
        [
            "TCP turns an unreliable network into a reliable byte stream. Every byte is numbered, "
            "and the receiver acknowledges the next byte it expects, so a cumulative ACK confirms "
            "everything before it. Lost segments are found by timeouts or duplicate ACKs and sent "
            "again.",
            "The three-way handshake agrees initial sequence numbers in both directions before any "
            "data moves. Flow control then keeps the sender within the receive window the other "
            "side advertises, so a slow receiver is never overrun.",
        ],
    ),
    (
        "Congestion control in my own words",
        [
            "Congestion control protects the network rather than the receiver. The sender keeps a "
            "congestion window and sends no more than the smaller of that window and the receive "
            "window.",
            "In slow start the window doubles every round trip until it reaches the slow start "
            "threshold. From there congestion avoidance adds about one segment per round trip. "
            "When a loss is detected the threshold drops to half the window in flight, which is "
            "the multiplicative decrease in AIMD.",
            "Three duplicate ACKs trigger fast retransmit and fast recovery, which keep the window "
            "at half instead of starting again from one segment. Only a timeout sends the "
            "connection back to slow start.",
        ],
    ),
]

# The session screenshot's tutor exchange: original text about the demo's own slides.
TUTOR_QUESTION = "Why does slow start stop doubling at ssthresh?"
TUTOR_ANSWER = (
    "In slow start every ACK grows the congestion window by one segment, so **cwnd doubles "
    "every round trip** [S1]. That finds the path's capacity quickly, but the growth is "
    "exponential【S1】.\n\n"
    "The slow start threshold is where slow start hands over to congestion avoidance: above "
    "it, cwnd grows by only about one segment per round trip [S2]. After a loss, ssthresh "
    "drops to half the window in flight [S2][S3]:\n\n"
    "$$\n\\text{ssthresh} = \\frac{\\text{flight size}}{2}\n$$"
)
# (label, material, page, cited): what the answer was given, in rank order.
TUTOR_SOURCES = [
    ("S1", "Week 6 slides", 3, True),
    ("S2", "Week 6 slides", 4, True),
    ("S3", "TCP notes", 2, True),
    ("S4", "Week 6 slides", 5, False),
    ("S5", "Week 6 slides", 6, False),
]

# "Quiz me" on that answer: original questions on the demo's own slides (no AI call).
TUTOR_QUIZ = {
    "questions": [
        {
            "prompt": "In slow start, how does cwnd grow?",
            "options": [
                "By one segment per round trip",
                "It doubles every round trip",
                "It halves after every ACK",
                "It stays fixed until a loss",
            ],
            "correct": 1,
            "explanation": "Each ACK adds one segment, so cwnd doubles every round trip [S1].",
            "sources": ["S1"],
        },
        {
            "prompt": "What happens to ssthresh after a loss?",
            "options": [
                "It is set to half the window in flight",
                "It doubles",
                "It is reset to one segment",
                "It is left unchanged",
            ],
            "correct": 0,
            "explanation": "After a loss ssthresh is set to half the window in flight [S2].",
            "sources": ["S2"],
        },
        {
            "prompt": "Above ssthresh, how much does cwnd grow per round trip?",
            "options": [
                "It doubles",
                "About one segment",
                "Half a window",
                "Nothing until the next loss",
            ],
            "correct": 1,
            "explanation": "Above it cwnd grows by about one segment per round trip [S2].",
            "sources": ["S2"],
        },
    ]
}

# (topic, description, children: (name, description, cited pages as (material, page)))
TREE = [
    (
        "TCP reliable transport",
        "How TCP turns an unreliable network into a reliable byte stream.",
        [
            (
                "Three-way handshake",
                "Agreeing initial sequence numbers before data flows.",
                [("Week 5 slides", 2), ("TCP notes", 1)],
            ),
            (
                "Sequence numbers and ACKs",
                "Cumulative acknowledgement of a numbered byte stream.",
                [("Week 5 slides", 3), ("TCP notes", 1)],
            ),
            (
                "Flow control",
                "Keeping the sender within the receiver's advertised window.",
                [("Week 5 slides", 4)],
            ),
            (
                "Retransmission timeout",
                "Resending segments that were never acknowledged.",
                [("Week 5 slides", 5)],
            ),
        ],
    ),
    (
        "TCP congestion control",
        "Sharing a bottleneck link without overflowing the routers' queues.",
        [
            (
                "Slow start and ssthresh",
                "Exponential window growth up to the slow start threshold.",
                [("Week 6 slides", 3), ("Week 6 slides", 4), ("TCP notes", 2)],
            ),
            (
                "Congestion avoidance (AIMD)",
                "Additive increase, multiplicative decrease.",
                [("Week 6 slides", 5), ("TCP notes", 2)],
            ),
            (
                "Fast retransmit and fast recovery",
                "Reacting to three duplicate ACKs.",
                [("Week 6 slides", 6)],
            ),
        ],
    ),
]


# Practice (Phase 5 task 4): synthetic cards on general TCP facts, written for the demo. Each
# card's reviews are (days before ``now``, grade); grade -1 is an Again 5 minutes before
# ``now`` (a learning step). Topics are chosen so one reads strong, one developing and one
# weak, with cards due now, one in its learning step and new ones. The AI-written short
# answer cites the demo's own slides (origin "ai"), so its source chip opens the page.
Card = tuple[str, str, list[str] | None, list[tuple[float, int]]]
PRACTICE: list[tuple[str, list[Card]]] = [
    (
        "Three-way handshake",
        [
            (
                "Which segment opens a TCP connection?",
                "A SYN from the client.",
                None,
                [(9, 3), (5, 3), (1, 4)],
            ),
            (
                "What does the server send back to a SYN?",
                "A SYN-ACK: its own SYN, acknowledging the client's.",
                None,
                [(9, 3), (5, 3), (1, 3)],
            ),
            (
                "What completes the three-way handshake?",
                "The client's ACK of the server's SYN.",
                None,
                [(9, 3), (5, 4), (1, 3)],
            ),
            (
                "Why does each side choose an initial sequence number?",
                "So both ends agree where their byte stream starts.",
                None,
                [(9, 3), (5, 3), (1, 3)],
            ),
        ],
    ),
    (
        "Slow start and ssthresh",
        [
            (
                "How does the congestion window grow during slow start?",
                "It doubles every round trip.",
                None,
                [(6, 3), (3, 2)],
            ),
            (
                "What happens when the congestion window reaches ssthresh?",
                "Slow start ends and congestion avoidance begins.",
                None,
                [(6, 3), (2, 3)],
            ),
            (
                "Why does slow start stop doubling at ssthresh?",
                "ssthresh marks the window size that was safe last time, so past it the sender "
                "grows by one segment per round trip instead, to avoid overflowing router queues.",
                [
                    "ssthresh marks a window size that was safe",
                    "Past it, growth becomes additive",
                    "This avoids overflowing router queues",
                ],
                [(6, 2), (3, 1)],
            ),
        ],
    ),
    (
        "Fast retransmit and fast recovery",
        [
            (
                "What triggers a fast retransmit?",
                "Three duplicate ACKs for the same segment.",
                None,
                [(4, 1), (2, 1)],
            ),
            (
                "What does fast recovery set the congestion window to?",
                "About half its old value (the new ssthresh), not one segment.",
                None,
                [(4, 1), (2, 2)],
            ),
            (
                "Why retransmit before the timeout fires?",
                "Duplicate ACKs show later segments arrived, so only one was lost and waiting "
                "for the timeout would waste time.",
                [
                    "Duplicate ACKs show later segments arrived",
                    "So only one segment was lost",
                    "Waiting for the timeout wastes time",
                ],
                [(4, 1), (2, 1), (0, -1)],
            ),
        ],
    ),
    (
        "Retransmission timeout",
        [
            (
                "What does TCP do when the retransmission timer expires?",
                "It resends the oldest unacknowledged segment.",
                None,
                [],
            ),
            (
                "Why does the timeout double after each expiry?",
                "Backing off avoids flooding a network that may be congested.",
                None,
                [],
            ),
        ],
    ),
    (
        "Flow control",
        [
            (
                "Who sets the advertised window?",
                "The receiver, from its free buffer space.",
                None,
                [],
            ),
        ],
    ),
]
# The short answer citing the slides is written by the AI; its source is this slide.
PRACTICE_AI = {"Why does slow start stop doubling at ssthresh?": ("Week 6 slides", 3)}


async def practice(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    module_id: uuid.UUID,
    topic_ids: dict[str, uuid.UUID],
    materials: dict[str, uuid.UUID],
    now: datetime,
) -> str:
    """The practice items and their reviews (``PRACTICE``), through the real services, each
    review at its own past time. Returns the practised topics' bands, for the log."""
    for topic, cards in PRACTICE:
        for prompt, answer, key_points, plan in cards:
            created = await items.create_item(
                db,
                ItemCreate(
                    module_id=module_id,
                    topic_id=topic_ids[topic],
                    kind="short_answer" if key_points else "flashcard",
                    prompt=prompt,
                    answer=answer,
                    key_points=key_points,
                ),
                user_id=user_id,
            )
            if prompt in PRACTICE_AI:
                title, page = PRACTICE_AI[prompt]
                chunk = await db.scalar(
                    select(Chunk.id)
                    .where(
                        Chunk.user_id == user_id,
                        Chunk.material_id == materials[title],
                        Chunk.page_number == page,
                    )
                    .order_by(Chunk.position)
                    .limit(1)
                )
                assert chunk is not None
                await db.execute(
                    update(PracticeItem)
                    .where(PracticeItem.id == created.id)
                    .values(origin="ai", provider="groq", model="openai/gpt-oss-120b")
                )
                db.add(
                    PracticeItemSource(
                        item_id=created.id, user_id=user_id, chunk_id=chunk, label="S1"
                    )
                )
                await db.commit()
            for days, grade in plan:
                at = now - timedelta(minutes=5) if grade == -1 else now - timedelta(days=days)
                await review_item(
                    db,
                    created.id,
                    ReviewIn(grade=1 if grade == -1 else grade),
                    user_id=user_id,
                    now=at,
                )
    found = await module_mastery(db, module_id, user_id=user_id, at=now)
    practised = {name for name, cards in PRACTICE if any(plan for *_, plan in cards)}
    return ", ".join(
        f"{t.name} {t.mastery.band} ({t.mastery.value:.2f})" for t in found if t.name in practised
    )


async def make_session(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    module_id: uuid.UUID,
    topic_id: uuid.UUID,
    start: datetime,
    minutes: int,
    focus: int,
    covered: str,
) -> None:
    """A finished session: focus with one 5-minute break, then a reflection."""
    study, _ = await sessions.start_session(
        db,
        SessionStart.model_validate(
            {
                "module_id": module_id,
                "topic_id": topic_id,
                "start": {"id": uuid.uuid4(), "occurred_at": start},
            }
        ),
        user_id=user_id,
    )
    half = minutes // 2
    steps = [("break_start", half), ("break_end", half + 5), ("end", minutes + 5)]
    events = [
        {"id": uuid.uuid4(), "type": kind, "occurred_at": start + timedelta(minutes=offset)}
        for kind, offset in steps
    ]
    await sessions.add_events(
        db, study.id, EventBatch.model_validate({"events": events}), user_id=user_id
    )
    await sessions.set_reflection(
        db,
        study.id,
        ReflectionIn.model_validate(
            {
                "focus_rating": focus,
                "covered_notes": covered,
                "topic_ratings": [{"topic_id": topic_id, "confidence": min(5, focus)}],
            }
        ),
        user_id=user_id,
    )


async def plan_history(db: AsyncSession, *, user_id: uuid.UUID, now: datetime) -> None:
    """Monday to Wednesday of ``now``'s week, through the real re-plan code: one hour of study
    time on each of those evenings (so one block a day), version 1 from Monday at 08:00,
    Monday's block studied (a linked session) and Tuesday's skipped; Wednesday's is left to be
    marked missed by the next re-plan."""
    tz = ZoneInfo(TIMEZONE)
    local = now.astimezone(tz)
    monday = (local - timedelta(days=local.weekday())).replace(
        hour=8, minute=0, second=0, microsecond=0
    )
    if local - monday < timedelta(days=2, hours=11):  # Wednesday 19:00, after its block
        raise SystemExit("--now must be after Wednesday 19:00 in its week: the plan needs history")
    for offset in range(3):
        db.add(
            AvailabilityException(
                user_id=user_id,
                date=(monday + timedelta(days=offset)).date(),
                unavailable=False,
                windows=[{"start": 18 * 60, "end": 19 * 60}],
                note="Busy start to the week",
            )
        )
    await db.commit()
    await replan(db, user_id=user_id, now=monday, trigger="initial")

    async def first_block(day: int) -> PlanBlock:
        version = await current_version(db, user_id=user_id)
        assert version is not None
        found = await db.scalar(
            select(PlanBlock)
            .where(
                PlanBlock.version_id == version.id,
                PlanBlock.status == "planned",
                PlanBlock.kind == "study",
                PlanBlock.start_at >= monday + timedelta(days=day),
                PlanBlock.start_at < monday + timedelta(days=day + 1),
            )
            .order_by(PlanBlock.start_at)
            .limit(1)
        )
        if found is None:
            raise SystemExit(f"No study block on day {day} of the demo week")
        return found

    done = await first_block(0)
    began = done.start_at + timedelta(minutes=2)
    study, _ = await sessions.start_session(
        db,
        SessionStart.model_validate(
            {
                "module_id": done.module_id,
                "topic_id": done.topic_id,
                "plan_block_id": done.id,
                "start": {"id": uuid.uuid4(), "occurred_at": began},
            }
        ),
        user_id=user_id,
    )
    end = {"id": uuid.uuid4(), "type": "end", "occurred_at": began + timedelta(minutes=46)}
    await sessions.add_events(
        db, study.id, EventBatch.model_validate({"events": [end]}), user_id=user_id
    )
    await replan(db, user_id=user_id, now=began + timedelta(minutes=50), trigger="finish")
    skipped = await first_block(1)
    await skip_block(db, skipped.id, user_id=user_id, now=monday + timedelta(days=1))


async def seed(now: datetime) -> None:
    settings = get_settings()
    database = make_url(settings.database_url).database or ""
    if not database.endswith("_demo"):
        raise SystemExit(
            f"Refusing to seed demo data into {database!r}: the name must end in _demo"
        )
    sessionmaker = get_sessionmaker()
    storage = get_storage()
    async with sessionmaker() as db:
        user = await db.scalar(select(User).where(User.email == settings.local_user_email))
        if user is None:
            raise SystemExit("No local user: run `python -m app.seed` first.")
        uid = user.id
        module = await modules.create_module(
            db,
            ModuleCreate(
                code="NET201", name="Computer Networks", colour="#FF7A3D", semester="2026 S2"
            ),
            user_id=uid,
        )
        module_id = module.id

        topic_ids: dict[str, uuid.UUID] = {}
        citations: list[tuple[uuid.UUID, str, int]] = []
        for name, description, children in TREE:
            parent = await topics.create_topic(
                db, module_id, TopicCreate(name=name, description=description), user_id=uid
            )
            topic_ids[name] = parent.id
            for child, child_description, pages in children:
                node = await topics.create_topic(
                    db,
                    module_id,
                    TopicCreate(name=child, description=child_description, parent_id=parent.id),
                    user_id=uid,
                )
                topic_ids[child] = node.id
                citations += [(node.id, material, page) for material, page in pages]

        day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        test = await assessments.create_assessment(
            db,
            module_id,
            AssessmentCreate(
                title="Semester test 2",
                kind="test",
                weight=25,
                due_at=day + timedelta(days=3, hours=9),
                topic_ids=[
                    topic_ids["TCP reliable transport"],
                    topic_ids["TCP congestion control"],
                ],
            ),
            user_id=uid,
        )
        assignment = await assessments.create_assessment(
            db,
            module_id,
            AssessmentCreate(
                title="Assignment 3: congestion control",
                kind="assignment",
                weight=10,
                due_at=day + timedelta(days=6, hours=23, minutes=59),
                topic_ids=[topic_ids["TCP congestion control"]],
            ),
            user_id=uid,
        )
        for title, assessment_id, due_days, status in [
            ("Re-read the slow start slides", test.id, 1, "todo"),
            ("Practise sequence-number questions", test.id, 2, "in_progress"),
            ("Plot cwnd over time for Assignment 3", assignment.id, 5, "todo"),
        ]:
            await tasks.create_task(
                db,
                module_id,
                TaskCreate(
                    title=title,
                    assessment_id=assessment_id,
                    status=status,
                    due_at=day + timedelta(days=due_days, hours=18),
                ),
                user_id=uid,
            )

        # Study time for the planner: weekday evenings, and two windows on Saturday and one on
        # Sunday afternoon (the daily cap stays at the default 3 h).
        weekly = [(d, 18 * 60, 21 * 60) for d in range(5)] + [
            (5, 9 * 60, 12 * 60),
            (5, 14 * 60, 17 * 60),
            (6, 14 * 60, 17 * 60),
        ]
        for weekday, start_minute, end_minute in weekly:
            db.add(
                AvailabilityRule(
                    user_id=uid, weekday=weekday, start_minute=start_minute, end_minute=end_minute
                )
            )
        # One self-rated topic with the student's own time for the whole chapter, so the plan
        # has work left after the week of sessions and shows a low-confidence block.
        congestion = await db.get(Topic, topic_ids["TCP congestion control"])
        assert congestion is not None
        congestion.confidence = 2
        congestion.estimated_minutes = 240
        await db.commit()

        # A week of study before `now`: one session a day on six of the seven days.
        week = [
            (7, "Three-way handshake", 50, 4, "Handshake and initial sequence numbers"),
            (6, "Sequence numbers and ACKs", 40, 3, "Cumulative ACKs, worked examples"),
            (5, "Flow control", 25, 4, "Receive window and zero-window probes"),
            (3, "Slow start and ssthresh", 50, 5, "Slow start up to ssthresh"),
            (2, "Congestion avoidance (AIMD)", 45, 4, "AIMD sawtooth"),
            (1, "Fast retransmit and fast recovery", 30, 3, "Duplicate ACKs and fast recovery"),
        ]
        for days_ago, topic, minutes, focus, covered in week:
            await make_session(
                db,
                user_id=uid,
                module_id=module_id,
                topic_id=topic_ids[topic],
                start=day - timedelta(days=days_ago) + timedelta(hours=14),
                minutes=minutes,
                focus=focus,
                covered=covered,
            )
        await plan_history(db, user_id=uid, now=now)

        files: list[tuple[str, str, MaterialKind, bytes]] = [
            ("week5-tcp.pdf", "Week 5 slides", "slides", slide_deck_pdf(RELIABLE)),
            ("week6-congestion.pdf", "Week 6 slides", "slides", slide_deck_pdf(CONGESTION)),
            ("tcp-notes.docx", "TCP notes", "notes", notes_docx(NOTES)),
        ]
        for filename, title, kind, body in files:
            await upload_material(
                db,
                storage,
                module_id,
                user_id=uid,
                source=io.BytesIO(body),
                filename=filename,
                kind=kind,
                title=title,
                allow_ai=True,
                max_bytes=settings.max_upload_bytes,
            )

    # The real pipeline: extract text, chunk, embed and index. Topic jobs would call the AI,
    # so they're removed before each run (the demo's topic tree is inserted below instead).
    # Re-plans are removed too: they'd plan at the real time, not the demo's ``now``.
    ran = 0
    while True:
        async with sessionmaker() as db:
            await db.execute(
                delete(Job).where(Job.kind.in_((EXTRACT_TOPICS, MERGE_TOPICS, LINK_TOPICS, REPLAN)))
            )
            await db.commit()
        if not await run_once(sessionmaker, storage):
            break
        ran += 1

    async with sessionmaker() as db:
        materials = {
            title: material_id
            for material_id, title in await db.execute(
                select(Material.id, Material.title).where(Material.module_id == module_id)
            )
        }
        states = list(
            await db.scalars(select(Material.status).where(Material.module_id == module_id))
        )
        if states != ["ready"] * len(files):
            raise SystemExit(f"Materials didn't all index: {states}")
        for topic_id, material, page in citations:
            db.add(
                TopicPage(
                    user_id=uid,
                    module_id=module_id,
                    topic_id=topic_id,
                    material_id=materials[material],
                    page_number=page,
                )
            )
        await db.commit()
        links = await link_module(
            db,
            module_id,
            user_id=uid,
            embedder=await asyncio.to_thread(get_embedder),
            threshold=settings.topic_link_threshold,
            max_chunks=settings.topic_link_max_chunks,
            min_page_chars=settings.topic_link_min_page_chars,
        )
        await db.commit()

        bands = await practice(
            db,
            user_id=uid,
            module_id=module_id,
            topic_ids=topic_ids,
            materials=materials,
            now=now,
        )

        # The session the screenshot shows, 18 minutes in, and its tutor conversation.
        study, _ = await sessions.start_session(
            db,
            SessionStart.model_validate(
                {
                    "module_id": module_id,
                    "topic_id": topic_ids["Slow start and ssthresh"],
                    # One second early: the screenshot's clock stands at now + 1 s.
                    "start": {
                        "id": uuid.uuid4(),
                        "occurred_at": now - timedelta(minutes=18) + timedelta(seconds=1),
                    },
                }
            ),
            user_id=uid,
        )
        conversation = Conversation(
            user_id=uid,
            module_id=module_id,
            study_session_id=study.id,
            topic_id=topic_ids["Slow start and ssthresh"],
        )
        db.add(conversation)
        await db.flush()
        db.add(
            Message(
                user_id=uid,
                conversation_id=conversation.id,
                position=0,
                role="user",
                mode="answer",
                text=TUTOR_QUESTION,
                status="complete",
            )
        )
        answer = Message(
            user_id=uid,
            conversation_id=conversation.id,
            position=1,
            role="assistant",
            mode="answer",
            text=TUTOR_ANSWER,
            status="complete",
            model="groq/openai/gpt-oss-120b",
            first_token_ms=640,
            total_ms=2100,
        )
        titles = await db.execute(
            select(MaterialPage.material_id, MaterialPage.page_number, MaterialPage.title).where(
                MaterialPage.user_id == uid
            )
        )
        page_titles = {(material, page): title for material, page, title in titles}
        answer.sources = [
            MessageSource(
                user_id=uid,
                label=label,
                rank=int(label[1:]),
                material_id=materials[material],
                material_title=material,
                page_number=page,
                page_title=page_titles.get((materials[material], page)),
                cited=cited,
            )
            for label, material, page, cited in TUTOR_SOURCES
        ]
        db.add(answer)
        db.add(
            Message(
                user_id=uid,
                conversation_id=conversation.id,
                position=2,
                role="user",
                mode="quiz",
                text="Quiz me",
                status="complete",
            )
        )
        quiz = Message(
            user_id=uid,
            conversation_id=conversation.id,
            position=3,
            role="assistant",
            mode="quiz",
            text="Quiz: 3 questions.",
            status="complete",
            model="groq/openai/gpt-oss-120b",
            total_ms=2400,
            quiz=Quiz.model_validate(TUTOR_QUIZ).model_dump(mode="json"),
            quiz_answers=[None, None, None],
        )
        quiz.sources = [
            MessageSource(
                user_id=uid,
                label=label,
                rank=int(label[1:]),
                material_id=materials[material],
                material_title=material,
                page_number=page,
                page_title=page_titles.get((materials[material], page)),
                cited=label in ("S1", "S2"),
            )
            for label, material, page, _ in TUTOR_SOURCES
        ]
        db.add(quiz)
        await db.commit()
    async with sessionmaker() as db:
        await db.execute(delete(Job).where(Job.kind == REPLAN))
        await db.commit()
        # The plan for the week view and Today: the nightly re-plan at 03:00 on ``now``'s day
        # (Wednesday's block is marked missed; tonight's is in progress at ``now``).
        user = await db.scalar(select(User).where(User.email == settings.local_user_email))
        assert user is not None
        night = now.astimezone(ZoneInfo(TIMEZONE)).replace(
            hour=3, minute=0, second=0, microsecond=0
        )
        await replan(db, user_id=user.id, now=night, trigger="nightly")
    print(
        f"Demo seeded: NET201, {len(files)} materials ({ran} jobs), {len(week)} sessions "
        f"and one open, {len(topic_ids)} topics, {links} chunk links, "
        f"one tutor exchange and a quiz; practice: {bands}."
    )
    await get_engine().dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--now", required=True, help="the demo's 'now', ISO 8601 with offset")
    now = datetime.fromisoformat(parser.parse_args().now)
    if now.tzinfo is None:
        raise SystemExit("--now needs a UTC offset, e.g. 2026-11-16T10:40:00+02:00")
    asyncio.run(seed(now))


if __name__ == "__main__":
    main()
