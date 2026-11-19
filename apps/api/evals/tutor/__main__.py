"""Tutor eval: ``uv run --directory apps/api python -m evals.tutor cos330 --label run1``.

**Real AI calls on the free tier** (about 25 a run), read-only against the dev database,
never in CI. Each question goes through the tutor's own service in answer mode, as the CLI's
dry run does (``app/tutor/ask.py``): retrieval with the question's topic, the prompt, the
streamed answer. Nothing is written: the session is read-only in Postgres, and usage is
kept in memory (today's earlier calls still count toward the daily budgets).

**Pacing:** Groq's free tier allows 8,000 tokens a minute for gpt-oss-120b. Before each call
the runner waits until the tokens of the last minute's Groq calls plus an estimate of this
request stay under ``TOKENS_A_MINUTE`` (7,000), so the limit isn't what's measured. Any call
turned away anyway is counted in the results.

Per question it records the sources, the cited labels and pages, whether a cited page is
acceptable, coverage (of the acceptable pages among the sources, the share cited), whether
it said the material doesn't cover it, the time to first token and the model. "Quiz me"
runs after the questions in ``quiz_after``, on that answer's sources.

**Outputs:**
- ``evals/results/tutor-<date>[-<label>].json``: numbers, labels and page references
  only, never answer or course text (committed);
- ``--review FILE``: the answers and the quiz questions, for checking by hand (keep it
  outside the repository: it holds AI text about the course).
"""

import argparse
import asyncio
import hashlib
import io
import json
import sys
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from app.ai.client import LLMClient, TextDelta
from app.ai.errors import AIUnavailable
from app.ai.usage import UsageRecord
from app.core.config import Settings, get_settings
from app.services.search.embedding import get_embedder
from app.services.tutor.prompts import TUTOR_SYSTEM, estimate_tokens
from app.services.tutor.quiz import QUIZ_SYSTEM, build_quiz
from app.services.tutor.retrieval import PreviousSource
from app.services.tutor.turn import Answer, answer, build_turn
from app.tutor.ask import MemoryUsage, Sessions, read_only_sessions
from evals.common import EVALS_DIR, find_module, load_config
from evals.metrics import Page, coverage, mean, percentile, rate, says_not_covered
from evals.search.retrieval import find_topic

TOKENS_A_MINUTE = 7000
# Kept for the reply (and gpt-oss's thinking) when estimating a request.
REPLY_TOKENS = 1500
WINDOW = 60.0
RESULTS = EVALS_DIR / "results"


class TimedUsage(MemoryUsage):
    """Usage in memory, each row with when it was written (for pacing)."""

    def __init__(self, sessions: Sessions) -> None:
        super().__init__(sessions)
        self.times: list[float] = []

    async def record(self, row: UsageRecord) -> None:
        await super().record(row)
        self.times.append(time.monotonic())

    def groq_tokens_since(self, since: float) -> int:
        return sum(
            row.input_tokens + row.output_tokens
            for row, at in zip(self.rows, self.times, strict=True)
            if at >= since and row.provider == "groq"
        )


@dataclass
class Pacer:
    usage: TimedUsage
    waited: float = 0.0
    log: TextIO = sys.stdout

    async def before(self, request: str | int) -> None:
        """Wait until the request (its text, or its estimated tokens) fits the minute."""
        size = estimate_tokens(request) if isinstance(request, str) else request
        need = size + REPLY_TOKENS
        while self.usage.groq_tokens_since(time.monotonic() - WINDOW) + need > TOKENS_A_MINUTE:
            await asyncio.sleep(5)
            self.waited += 5


@dataclass
class Question:
    number: int
    query: str
    topic: dict[str, str]
    pages: list[Page]


def questions_of(config: dict[str, Any]) -> list[Question]:
    found = load_config(config["search_queries"])["queries"] + config["questions"]
    return [
        Question(n, q["query"], q["topic"], [(p["material"], int(p["page"])) for p in q["pages"]])
        for n, q in enumerate(found, start=1)
    ]


def prompt_id() -> str:
    """Which prompts were used (they change between runs): a short hash of both."""
    return hashlib.sha256((TUTOR_SYSTEM + QUIZ_SYSTEM).encode()).hexdigest()[:12]


@dataclass
class Run:
    questions: list[dict[str, Any]] = field(default_factory=list)
    quizzes: list[dict[str, Any]] = field(default_factory=list)


async def ask_one(
    session: Any,
    question: Question,
    *,
    module_id: uuid.UUID,
    user_id: uuid.UUID,
    embedder: Any,
    settings: Settings,
    client: LLMClient,
    pacer: Pacer,
    review: TextIO,
) -> tuple[dict[str, Any], list[PreviousSource]]:
    topic_id = await find_topic(session, module_id, user_id, question.topic)
    started = time.monotonic()
    turn = await build_turn(
        session,
        module_id,
        question.query,
        "answer",
        user_id=user_id,
        topic_id=topic_id,
        history=[],
        embedder=embedder,
        settings=settings,
        started=started,
    )
    retrieval_ms = int((time.monotonic() - started) * 1000)
    await pacer.before("\n".join(m.text for m in turn.messages))
    # Timings start once pacing is done: the wait is ours, not the tutor's.
    paced = time.monotonic()
    turn = replace(turn, started=paced - retrieval_ms / 1000)
    result: Answer | None = None
    async for event in answer(turn, client=client, user_id=user_id):
        if isinstance(event, Answer):
            result = event
        elif isinstance(event, TextDelta):
            pass
    assert result is not None
    by_label = {s.label: s for s in turn.sources}
    sources: list[Page] = [(s.material_title, s.page_number) for s in turn.sources]
    cited: list[Page] = [
        (by_label[label].material_title, by_label[label].page_number) for label in result.cited
    ]
    acceptable = set(question.pages)
    record = {
        "number": question.number,
        "question": question.query,
        "topic": question.topic["name"],
        "status": result.status,
        "model": result.model,
        "first_token_ms": result.first_token_ms,
        "total_ms": result.total_ms,
        "retrieval_ms": retrieval_ms,
        "context_tokens": turn.context_tokens,
        "sources": [
            {"label": s.label, "material": s.material_title, "page": s.page_number}
            for s in turn.sources
        ],
        "cited": result.cited,
        "cited_pages": [{"material": m, "page": p} for m, p in cited],
        "unknown_citations": result.unknown_citations,
        "acceptable_pages": [{"material": m, "page": p} for m, p in question.pages],
        "acceptable_in_sources": len(acceptable & set(sources)),
        "cites_acceptable": bool(acceptable & set(cited)),
        "coverage": coverage(cited, sources, acceptable),
        "said_not_covered": says_not_covered(result.text, result.cited),
        "error": result.error,
    }
    review.write(
        f"\n===== Q{question.number}: {question.query}\n"
        f"[{result.status} · {result.model} · first token {result.first_token_ms} ms]\n"
        f"{result.text}\n"
    )
    previous = [
        PreviousSource(s.label, s.chunk_id, s.material_id, s.page_number) for s in turn.sources
    ]
    return record, previous


async def quiz_one(
    session: Any,
    question: Question,
    previous: list[PreviousSource],
    *,
    user_id: uuid.UUID,
    settings: Settings,
    client: LLMClient,
    usage: TimedUsage,
    pacer: Pacer,
    review: TextIO,
) -> dict[str, Any]:
    # A quiz request: its prompt plus up to the full context budget of sources.
    await pacer.before(estimate_tokens(QUIZ_SYSTEM) + settings.tutor_context_max_tokens)
    first_row = len(usage.rows)
    try:
        quiz = await build_quiz(
            session,
            previous,
            focus=question.query,
            user_id=user_id,
            client=client,
            settings=settings,
        )
    except AIUnavailable as exc:
        return {"after": question.number, "error": str(exc), "questions": []}
    rows = [r for r in usage.rows[first_row:] if r.purpose == "tutor_quiz"]
    tried = [r for r in rows if r.outcome not in ("rate_limited", "overloaded", "too_large")]
    by_label = {s.label: s for s in quiz.sources}
    questions = []
    review.write(f"\n===== Quiz after Q{question.number} [{quiz.model} · {quiz.total_ms} ms]\n")
    for n, q in enumerate(quiz.quiz.questions if quiz.quiz else [], start=1):
        pages = [
            {
                "label": label,
                "material": by_label[label].material_title,
                "page": by_label[label].page_number,
            }
            for label in q.sources
            if label in by_label
        ]
        questions.append(
            {
                "number": n,
                "correct": q.correct,
                "sources": pages,
                # Filled in by hand after reading the cited pages (see the .md).
                "answer_supported": None,
                "a_wrong_option_is_also_true": None,
            }
        )
        review.write(f"\nQ{n}. {q.prompt}\n")
        for i, option in enumerate(q.options):
            review.write(f"  {'*' if i == q.correct else ' '} {'ABCD'[i]}. {option}\n")
        review.write(f"  Why: {q.explanation}\n  Pages: {pages}\n")
    return {
        "after": question.number,
        "model": quiz.model,
        "total_ms": quiz.total_ms,
        "calls": [f"{r.provider}/{r.model} {r.outcome}" for r in rows],
        "valid_first_try": bool(tried) and tried[0].outcome == "ok",
        "kept": len(questions),
        "dropped": quiz.dropped,
        "error": quiz.error,
        "questions": questions,
    }


def totals(records: list[dict[str, Any]]) -> dict[str, Any]:
    times = [float(r["first_token_ms"]) for r in records if r["first_token_ms"] is not None]
    return {
        "questions": len(records),
        "cites_an_acceptable_page": sum(1 for r in records if r["cites_acceptable"]),
        "correct_page_citation_rate": rate([r["cites_acceptable"] for r in records]),
        "mean_coverage": mean([r["coverage"] for r in records]),
        "coverage_measured_for": sum(1 for r in records if r["coverage"] is not None),
        "said_not_covered": sum(1 for r in records if r["said_not_covered"]),
        "failed": sum(1 for r in records if r["status"] == "failed"),
        "first_token_ms_median": percentile(times, 50),
        "first_token_ms_p90": percentile(times, 90),
        "first_token_ms_max": max(times) if times else None,
        "models": dict(Counter(str(r["model"]) for r in records)),
    }


async def main(name: str, label: str | None, review_path: Path | None) -> int:
    config = load_config(f"tutor/{name}.yaml")
    questions = questions_of(config)
    quiz_after = set(config.get("quiz_after", []))
    settings = get_settings()
    embedder = await asyncio.to_thread(get_embedder)  # loaded before any timing
    review = io.StringIO()
    run = Run()
    began = datetime.now(UTC)
    try:
        async with read_only_sessions(settings) as sessions:
            usage = TimedUsage(sessions)
            client = LLMClient(settings, usage)
            pacer = Pacer(usage)
            try:
                async with sessions() as session:
                    module_id, user_id = await find_module(session, config["module"])
                    for question in questions:
                        record, previous = await ask_one(
                            session,
                            question,
                            module_id=module_id,
                            user_id=user_id,
                            embedder=embedder,
                            settings=settings,
                            client=client,
                            pacer=pacer,
                            review=review,
                        )
                        run.questions.append(record)
                        print(
                            f"{question.number:>2} {record['status']:<9} "
                            f"{record['model']!s:<28} ttft {record['first_token_ms']} ms  "
                            f"cited {record['cited']}  acceptable {record['cites_acceptable']}",
                            flush=True,
                        )
                        if question.number in quiz_after:
                            quiz = await quiz_one(
                                session,
                                question,
                                previous,
                                user_id=user_id,
                                settings=settings,
                                client=client,
                                usage=usage,
                                pacer=pacer,
                                review=review,
                            )
                            run.quizzes.append(quiz)
                            print(
                                f"   quiz: {quiz.get('kept', 0)} kept, "
                                f"{quiz.get('dropped', 0)} dropped, first try valid "
                                f"{quiz.get('valid_first_try')}  {quiz.get('calls')}",
                                flush=True,
                            )
            finally:
                await client.aclose()
            calls = Counter(f"{r.provider}/{r.model} {r.outcome}" for r in usage.rows)
            waited = pacer.waited
    finally:
        if review_path is not None:
            await asyncio.to_thread(review_path.write_text, review.getvalue(), "utf-8")

    result = {
        "eval": f"tutor/{name}",
        "label": label,
        "started_at": began.isoformat(timespec="seconds"),
        "prompts": prompt_id(),
        "settings": {
            "tutor_topic_boost": settings.tutor_topic_boost,
            "tutor_context_max_tokens": settings.tutor_context_max_tokens,
            "ai_smart": [route.route for route in settings.ai_smart],
        },
        "pacing": {"tokens_a_minute": TOKENS_A_MINUTE, "seconds_waited": waited},
        "calls": dict(calls),
        "free_tier_calls": sum(calls.values()),
        "totals": totals(run.questions),
        "questions": run.questions,
        "quizzes": run.quizzes,
    }
    RESULTS.mkdir(exist_ok=True)
    stem = f"tutor-{began:%Y-%m-%d}" + (f"-{label}" if label else "")
    out = RESULTS / f"{stem}.json"
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"\nTotals: {json.dumps(result['totals'], indent=2)}\nWrote {out}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="python -m evals.tutor")
    parser.add_argument("name", nargs="?", default="cos330")
    parser.add_argument("--label", help="added to the results file name, e.g. run2")
    parser.add_argument("--review", type=Path, help="write answers and quizzes here (not in git)")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(asyncio.run(main(args.name, args.label, args.review)))
