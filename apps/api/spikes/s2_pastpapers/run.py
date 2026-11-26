"""Running S2's candidates on the free tier (real AI calls, local only).

Each step writes its outputs under ``.local/`` (gitignored: they hold course text) and is
skipped on a later run when its output is there, so a run can stop at a rate limit and go on
later. Each step's cost (calls, tokens, seconds, failures, turned-away requests, the models
that answered) is written beside its outputs; ``score`` reads them.

The database session is read-only, and usage is kept in memory (today's earlier calls still
count toward the daily budgets), so nothing is written to the app.
"""

import asyncio
import json
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

import pypdfium2 as pdfium
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LLMClient
from app.ai.errors import AIInvalidOutput, AIRequestFailed, AITruncated, AIUnavailable
from app.ai.messages import Image, Message
from app.ai.routes import AIRole
from app.ai.usage import TURNED_AWAY_OUTCOMES
from app.core.config import get_settings
from app.models import Chunk, ChunkTopic, Material, MaterialPage, Module, Topic
from app.services.search.embedding import get_embedder
from app.services.tutor.prompts import estimate_tokens
from app.storage.base import blob_key
from app.storage.local import get_storage
from app.tutor.ask import read_only_sessions
from evals.tutor.__main__ import Pacer, TimedUsage
from spikes.s2_pastpapers import prompts
from spikes.s2_pastpapers.key import Key, KeyPaper
from spikes.s2_pastpapers.metrics import qualify
from spikes.s2_pastpapers.privacy import mask_png, redact_text
from spikes.s2_pastpapers.prompts import PageText, TopicOption
from spikes.s2_pastpapers.schemas import (
    PageSegmentation,
    PaperClassification,
    PartClassification,
    Segmentation,
    SegmentedPart,
)
from spikes.s2_pastpapers.text import Anchor, cut_parts, needs_transcription

LOCAL = Path(__file__).resolve().parent / ".local"
# Page images are rendered this wide (pixels): readable marks, a modest image token count.
RENDER_WIDTH = 1600
# A request turned away as busy is tried again this many times, waiting at most this long.
TRIES = 5
MAX_WAIT = 120.0
# Candidate topics per part for C2.
CANDIDATES = 8
# The Groq pacer can't wait for more than a minute's budget: larger requests go anyway.
PACE_CAP = 5000
# Material kinds whose chunks stand for topics in C2 (never past papers or the study guide,
# which quotes the papers).
TOPIC_EVIDENCE_EXCLUDED = ("past_paper", "test", "study_guide")

STEPS = ("transcribe", "seg-a", "seg-b", "c1", "c2")
# Which segmentation each classification runs on.
SEGMENTATIONS = ("seg-a", "seg-b")


@dataclass
class Cost:
    calls: int = 0
    turned_away: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    failures: int = 0  # units of work (a page, a paper, a part) with no usable reply
    units: int = 0
    models: dict[str, int] = field(default_factory=dict)

    def add(self, other: "Cost") -> None:
        self.calls += other.calls
        self.turned_away += other.turned_away
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.seconds = round(self.seconds + other.seconds, 1)
        self.failures += other.failures
        self.units += other.units
        for model, n in other.models.items():
            self.models[model] = self.models.get(model, 0) + n


@dataclass
class PaperData:
    key: KeyPaper
    material_id: uuid.UUID
    pdf: Path
    # Page number → (is_scanned, text layer), for the pages not excluded.
    pages: dict[int, tuple[bool, str]]


@dataclass
class Context:
    module_id: uuid.UUID
    user_id: uuid.UUID
    papers: list[PaperData]
    options: list[TopicOption]  # every topic, chapters first in tree order
    chapter_of: dict[str, str]  # topic name → its chapter's name
    topic_codes: dict[uuid.UUID, str]


class Runner:
    def __init__(
        self, client: LLMClient, usage: TimedUsage, pacer: Pacer, ctx: Context, out: TextIO
    ) -> None:
        self.client = client
        self.usage = usage
        self.pacer = pacer
        self.ctx = ctx
        self.out = out
        # The "provider/model" that gave the last ``ask_json`` reply.
        self.last_model: str | None = None

    # --- calls -----------------------------------------------------------------------

    async def _waiting[T](self, make: Callable[[], Awaitable[T]], groq_tokens: int) -> T:
        for attempt in range(1, TRIES + 1):
            await self.pacer.before(min(groq_tokens, PACE_CAP))
            try:
                return await make()
            except AIUnavailable as exc:
                if attempt == TRIES or exc.retry_at is None:
                    raise
                wait = (exc.retry_at - datetime.now(UTC)).total_seconds()
                wait = min(MAX_WAIT, max(5.0, wait))
                print(f"    busy, waiting {wait:.0f} s", file=self.out, flush=True)
                await asyncio.sleep(wait)
        raise AssertionError("unreachable")

    async def ask_json[T: BaseModel](
        self, role: AIRole, messages: list[Message], schema: type[T], purpose: str, cost: Cost
    ) -> T | None:
        cost.units += 1
        size = sum(estimate_tokens(m.text) for m in messages)
        self.last_model = None
        try:
            result = await self._waiting(
                lambda: self.client.complete_json_result(
                    role, messages, schema, purpose=purpose, user_id=self.ctx.user_id
                ),
                size,
            )
        except (AIUnavailable, AIInvalidOutput, AIRequestFailed, AITruncated) as exc:
            cost.failures += 1
            print(f"    failed: {type(exc).__name__}", file=self.out, flush=True)
            return None
        self.last_model = result.route.key
        return result.value

    async def ask_text(self, messages: list[Message], purpose: str, cost: Cost) -> str | None:
        cost.units += 1
        try:
            return await self._waiting(
                lambda: self.client.complete_text(
                    "vision", messages, purpose=purpose, user_id=self.ctx.user_id
                ),
                0,  # images go to Gemini first; the vision role's Groq model is paced by RPM
            )
        except (AIUnavailable, AIRequestFailed, AITruncated) as exc:
            cost.failures += 1
            print(f"    failed: {type(exc).__name__}", file=self.out, flush=True)
            return None

    async def measured(self, step: str, work: Callable[[Cost], Awaitable[None]]) -> Cost:
        cost = Cost()
        first = len(self.usage.rows)
        started = time.monotonic()
        await work(cost)
        cost.seconds = round(time.monotonic() - started, 1)
        for row in self.usage.rows[first:]:
            if row.outcome in TURNED_AWAY_OUTCOMES:
                cost.turned_away += 1
            else:
                cost.calls += 1
                cost.input_tokens += row.input_tokens
                cost.output_tokens += row.output_tokens
                name = f"{row.provider}/{row.model}"
                cost.models[name] = cost.models.get(name, 0) + 1
        return cost

    # --- the paper's text -------------------------------------------------------------

    def transcript_path(self, paper: PaperData, page: int) -> Path:
        return LOCAL / "transcripts" / slug(paper.key.label) / f"p{page:02d}.txt"

    def page_texts(self, paper: PaperData) -> list[PageText]:
        """The text sent for each page: its transcription when it needed one (empty if
        that failed), else its text layer; names redacted either way."""
        out: list[PageText] = []
        for number, (scanned, layer) in sorted(paper.pages.items()):
            if needs_transcription(scanned, len(layer)):
                path = self.transcript_path(paper, number)
                text = path.read_text(encoding="utf-8") if path.is_file() else ""
            else:
                text = layer
            out.append(PageText(number, redact_text(text)))
        return out

    # --- steps ------------------------------------------------------------------------

    async def transcribe(self, paper: PaperData, cost: Cost) -> None:
        document = pdfium.PdfDocument(str(paper.pdf))
        try:
            for number, (scanned, layer) in sorted(paper.pages.items()):
                if not needs_transcription(scanned, len(layer)):
                    continue
                path = self.transcript_path(paper, number)
                if path.is_file():
                    continue
                page = document[number - 1]
                bitmap = page.render(scale=RENDER_WIDTH / page.get_width())
                png = to_png(bitmap.to_pil())
                png = mask_png(png, paper.key.mask.get(number, ()))
                print(f"  {paper.key.label} page {number}", file=self.out, flush=True)
                text = await self.ask_text(
                    prompts.transcription_messages(number, Image(png)), "s2_transcribe", cost
                )
                if text is not None:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(text, encoding="utf-8")
        finally:
            document.close()

    async def segment_a(self, paper: PaperData, cost: Cost) -> dict[str, Any] | None:
        print(f"  {paper.key.label}", file=self.out, flush=True)
        reply = await self.ask_json(
            "long",
            prompts.segmentation_messages(self.page_texts(paper)),
            Segmentation,
            "s2_segment_a",
            cost,
        )
        if reply is None:
            return None
        return reply.model_dump() | {"model": self.last_model}

    async def segment_b(self, paper: PaperData, cost: Cost) -> dict[str, Any] | None:
        parts: list[SegmentedPart] = []
        total: float | None = None
        last: str | None = None
        parent: str | None = None
        failed = False
        models: list[str | None] = []
        for page in self.page_texts(paper):
            print(f"  {paper.key.label} page {page.number}", file=self.out, flush=True)
            reply = await self.ask_json(
                "smart",
                prompts.page_segmentation_messages(page, last_number=last, open_parent=parent),
                PageSegmentation,
                "s2_segment_b",
                cost,
            )
            if reply is None:
                failed = True
                continue
            parts += reply.questions
            models.append(self.last_model)
            total = total if total is not None else reply.total_marks
            last, parent = reply.last_number or last, reply.open_parent
        merged = Segmentation(total_marks=total, questions=parts).model_dump()
        merged["pages_failed"] = failed
        merged["models"] = models
        return merged

    async def classify_c1(
        self, paper: PaperData, seg: dict[str, Any], cost: Cost
    ) -> dict[str, Any] | None:
        numbers = [qualify(q["number"], q["parent"]) for q in seg["questions"]]
        print(f"  {paper.key.label}: {len(numbers)} parts", file=self.out, flush=True)
        reply = await self.ask_json(
            "long",
            prompts.paper_classification_messages(
                self.page_texts(paper), numbers, self.ctx.options
            ),
            PaperClassification,
            "s2_classify_c1",
            cost,
        )
        if reply is None:
            return None
        return {
            "questions": [self.named(q.number, q.topics, q.type) for q in reply.questions],
            "model": self.last_model,
        }

    async def classify_c2(
        self, session: AsyncSession, paper: PaperData, seg: dict[str, Any], cost: Cost
    ) -> dict[str, Any]:
        text = prompts.paper_text(self.page_texts(paper))
        anchors = [
            Anchor(qualify(q["number"], q["parent"]), q["parent"], q["first_words"])
            for q in seg["questions"]
        ]
        cuts = cut_parts(text, anchors)
        found = sum(c.found for c in cuts)
        print(f"  {paper.key.label}: {len(cuts)} parts ({found} cut)", file=self.out, flush=True)
        out: list[dict[str, Any]] = []
        for cut, part in zip(cuts, seg["questions"], strict=True):
            options = await self.candidates(session, cut.text)
            reply = await self.ask_json(
                "smart",
                prompts.part_classification_messages(cut.number, part["marks"], cut.text, options),
                PartClassification,
                "s2_classify_c2",
                cost,
            )
            if reply is not None:
                allowed = {o.code for o in options}
                codes = [c for c in reply.topics if c in allowed] or reply.topics
                out.append(self.named(cut.number, codes, reply.type) | {"model": self.last_model})
        return {"questions": out, "cut": found, "parts": len(cuts)}

    def named(self, number: str, codes: Sequence[str], kind: str) -> dict[str, Any]:
        """Codes → topic names; codes not in the list are dropped and counted."""
        by_code = {o.code: o for o in self.ctx.options}
        known = [by_code[c] for c in codes if c in by_code]
        return {
            "number": number,
            "topics": [o.name for o in known],
            "chapter": known[0].chapter if known else None,
            "type": kind,
            "unknown_codes": len(codes) - len(known),
        }

    async def candidates(self, session: AsyncSession, text: str) -> list[TopicOption]:
        """The topics whose linked chunks are closest to ``text`` (the best chunk per topic),
        from learning material only."""
        vector = await asyncio.to_thread(get_embedder().embed_query, text[:2000])
        similarity = (1 - Chunk.embedding.cosine_distance(vector)).label("similarity")
        rows = await session.execute(
            select(ChunkTopic.topic_id, func.max(similarity))
            .join(Chunk, Chunk.id == ChunkTopic.chunk_id)
            .join(Material, Material.id == Chunk.material_id)
            .where(
                Chunk.user_id == self.ctx.user_id,
                Chunk.module_id == self.ctx.module_id,
                Material.user_id == self.ctx.user_id,
                Material.kind.not_in(TOPIC_EVIDENCE_EXCLUDED),
            )
            .group_by(ChunkTopic.topic_id)
            .order_by(func.max(similarity).desc())
            .limit(CANDIDATES)
        )
        by_code = {o.code: o for o in self.ctx.options}
        return [
            by_code[self.ctx.topic_codes[topic_id]]
            for topic_id, _ in rows
            if topic_id in self.ctx.topic_codes
        ]


def slug(label: str) -> str:
    return label.lower().replace(" ", "-")


def to_png(image: Any) -> bytes:
    import io

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


async def load_context(session: AsyncSession, key: Key) -> Context:
    module = (await session.scalars(select(Module).where(Module.code == key.module))).one()
    user_id, module_id = module.user_id, module.id
    topics = list(
        await session.scalars(
            select(Topic)
            .where(Topic.module_id == module_id, Topic.user_id == user_id)
            .order_by(Topic.position)
        )
    )
    by_id = {t.id: t for t in topics}

    def chapter(t: Topic) -> Topic:
        while t.parent_id is not None:
            t = by_id[t.parent_id]
        return t

    roots = [t for t in topics if t.parent_id is None]
    ordered: list[Topic] = []
    for root in roots:
        ordered.append(root)
        ordered += [t for t in topics if t.parent_id is not None and chapter(t).id == root.id]
    codes = {t.id: f"t{n}" for n, t in enumerate(ordered, start=1)}
    options = [TopicOption(codes[t.id], t.name, chapter(t).name) for t in ordered]

    storage = get_storage()
    papers: list[PaperData] = []
    for paper in key.papers:
        material = (
            await session.scalars(
                select(Material).where(
                    Material.module_id == module_id,
                    Material.user_id == user_id,
                    Material.title == paper.title,
                    Material.kind.in_(("past_paper", "test")),
                )
            )
        ).one()
        rows = await session.scalars(
            select(MaterialPage)
            .where(MaterialPage.material_id == material.id, MaterialPage.user_id == user_id)
            .order_by(MaterialPage.page_number)
        )
        pages = {
            p.page_number: (p.is_scanned, p.text)
            for p in rows
            if p.page_number not in paper.excluded_pages
        }
        papers.append(
            PaperData(
                paper,
                material.id,
                storage.path_for(blob_key(user_id, material.sha256)),
                pages,
            )
        )
    return Context(
        module_id,
        user_id,
        papers,
        options,
        {o.name: o.chapter for o in options},
        codes,
    )


async def run(
    key: Key, steps: Sequence[str], out: TextIO, on: Sequence[str] = SEGMENTATIONS
) -> None:
    settings = get_settings()
    async with read_only_sessions(settings) as sessions:
        usage = TimedUsage(sessions)
        client = LLMClient(settings, usage)
        try:
            async with sessions() as session:
                ctx = await load_context(session, key)
                runner = Runner(client, usage, Pacer(usage, log=out), ctx, out)
                for step in steps:
                    print(f"{step}:", file=out, flush=True)
                    await run_step(runner, session, step, on)
        finally:
            await client.aclose()


async def run_step(
    runner: Runner, session: AsyncSession, step: str, on: Sequence[str] = SEGMENTATIONS
) -> None:
    """``on``: the segmentations a classification step runs on."""
    ctx = runner.ctx
    if step == "transcribe":

        async def work(cost: Cost) -> None:
            for paper in ctx.papers:
                await runner.transcribe(paper, cost)

        save_cost(step, await runner.measured(step, work))
        return
    if step in ("seg-a", "seg-b"):
        segment = runner.segment_a if step == "seg-a" else runner.segment_b

        async def seg_work(cost: Cost) -> None:
            for paper in ctx.papers:
                path = LOCAL / step / f"{slug(paper.key.label)}.json"
                if path.is_file():
                    continue
                result = await segment(paper, cost)
                if result is not None:
                    write_json(path, result)

        save_cost(step, await runner.measured(step, seg_work))
        return
    for source in on:
        name = f"{step}-on-{source}"

        async def classify_work(cost: Cost, source: str = source, name: str = name) -> None:
            for paper in ctx.papers:
                path = LOCAL / name / f"{slug(paper.key.label)}.json"
                seg = read_json(LOCAL / source / f"{slug(paper.key.label)}.json")
                if path.is_file() or seg is None:
                    continue
                if step == "c1":
                    result = await runner.classify_c1(paper, seg, cost)
                else:
                    result = await runner.classify_c2(session, paper, seg, cost)
                if result is not None:
                    write_json(path, result)

        print(f" on {source}:", file=runner.out, flush=True)
        save_cost(name, await runner.measured(name, classify_work))


def save_cost(step: str, cost: Cost) -> None:
    """Costs add up across runs of a step (a run can stop at a limit and go on later)."""
    path = LOCAL / "costs.json"
    costs: dict[str, Any] = read_json(path) or {}
    total = Cost(**costs[step]) if step in costs else Cost()
    total.add(cost)
    costs[step] = asdict(total)
    write_json(path, costs)
