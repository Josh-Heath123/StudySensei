"""Seed synthetic demo data for the README screenshots: ``npm run screenshots`` runs this.

    DATABASE_URL=...studysensei_demo STORAGE_DIR=data/demo-materials \\
        uv run python -m scripts.demo_seed --now 2026-11-16T10:40:00+02:00

Dev only, and only against a database whose name ends in ``_demo``. Everything here is
original text written for the demo (never course material). It makes one module, two
assessments, open tasks, a week of finished study sessions, and two slide decks and a set of
notes on TCP, which go through the real pipeline (extraction, chunking, local embeddings and
indexing; no AI calls). The topic tree is inserted directly, with the pages each topic cites,
and linked to the chunks the way the app does it (cited pages plus local similarity).

It also opens a study session 18 minutes before ``now``, with one tutor exchange about it: a
question and a stored answer written for the demo (no AI call), citing the demo's own pages,
then a "Quiz me" on it, so the session and quiz screenshots show the tutor panel.
"""

import argparse
import asyncio
import io
import uuid
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.jobs.kinds import EXTRACT_TOPICS, LINK_TOPICS, MERGE_TOPICS
from app.jobs.worker import run_once
from app.models import (
    AvailabilityRule,
    Conversation,
    Job,
    Material,
    MaterialPage,
    Message,
    MessageSource,
    Topic,
    TopicPage,
    User,
)
from app.schemas.academics import AssessmentCreate, ModuleCreate, TaskCreate, TopicCreate
from app.schemas.materials import MaterialKind
from app.schemas.sessions import EventBatch, ReflectionIn, SessionStart
from app.schemas.tutor import Quiz
from app.services.academics import assessments, modules, tasks, topics
from app.services.materials import upload_material
from app.services.search.embedding import get_embedder
from app.services.sessions import sessions
from app.services.topic_maps.linking import link_module
from app.storage.local import get_storage
from tests.fixtures.make_fixtures import notes_docx, slide_deck_pdf

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
        # One self-rated topic, so the plan shows a low-confidence block.
        congestion = await db.get(Topic, topic_ids["TCP congestion control"])
        assert congestion is not None
        congestion.confidence = 2
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
    ran = 0
    while True:
        async with sessionmaker() as db:
            await db.execute(
                delete(Job).where(Job.kind.in_((EXTRACT_TOPICS, MERGE_TOPICS, LINK_TOPICS)))
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
    print(
        f"Demo seeded: NET201, {len(files)} materials ({ran} jobs), {len(week)} sessions "
        f"and one open, {len(topic_ids)} topics, {links} chunk links, "
        "one tutor exchange and a quiz."
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
