"""The LLM client: roles, fallback, backoff, daily budgets and usage logging (decision 0002).

    client = get_llm_client()
    text = await client.complete_text("smart", [system(...), user(...)],
                                      purpose="tutor", user_id=user.id)
    topics = await client.complete_json("smart", messages, TopicMap,
                                        purpose="topic_extraction", user_id=user.id)

A request with an image always uses the ``vision`` role, whatever role was asked for.
For each request it walks the role's routes in order and skips a route that is:
- on a provider without a key,
- cooling down after a 429 or 5xx, or
- out of its daily budget (counted from ``ai_usage`` since the provider's quota reset).

Failures (decisions 0007, 0008): only "this model can't take it now" moves on to the next
route: a 429, a 503 ("high demand"), a timeout, a lost connection, a 413 (request too large
for the model's limits), or a content refusal (a filtered or empty reply; no repair spent).
A 429 or 5xx is first retried on the same model after its Retry-After (or a jittered
backoff) when that's short. Another 5xx that persists raises ``AIUnavailable``, and any
other refusal (400, 401, 404…) raises ``AIRequestFailed``: neither cascades through the
fallbacks. A reply cut off at the output limit raises ``AITruncated`` (no repair). When
every route is out, ``AIUnavailable`` says when to try again.

Pacing: each model has a requests-per-minute limit (``AI_REQUESTS_PER_MINUTE``, the free
tier less a margin); a request waits its turn instead of collecting 429s. An optional
``CallBudget`` caps the provider calls (and repairs) for one unit of work across fallbacks.
Every request is logged in ``ai_usage``.

Privacy: the client sends exactly the messages it's given and nothing about the user.
Callers build prompts from course content gathered through ``app.ai.sources``, which
leaves out materials with ``allow_ai`` off.
"""

import asyncio
import json
import logging
import random
import re
import time
import uuid
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx
from pydantic import BaseModel, ValidationError

from app.ai.adapter import Completion, OpenAICompatAdapter, ProviderError
from app.ai.budget import next_reset, quota_zone, window_start
from app.ai.errors import (
    NOT_CONFIGURED,
    AICallLimitReached,
    AIInvalidOutput,
    AIRefused,
    AIRequestFailed,
    AITruncated,
    AIUnavailable,
)
from app.ai.messages import Message, has_images, system, user
from app.ai.messages import assistant as assistant_message
from app.ai.routes import AIRole, Route, routes_for
from app.ai.usage import UsageRecord, UsageStore
from app.core.config import ReasoningEffort, Settings

log = logging.getLogger("studysensei.ai")

BACKOFF_BASE_SECONDS = 2.0
# The whole of one ping, so a slow model can't hold up the others.
PING_TIMEOUT_SECONDS = 30.0
# After a failure with no hint of when to come back.
DEFAULT_COOLDOWN = timedelta(minutes=1)
# When every route failed with a plain error (a bad key, an unknown model).
ERROR_RETRY = timedelta(minutes=10)
PACING_WINDOW_SECONDS = 60.0
_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class AIResult[T]:
    """A validated reply and the route (provider + model) that gave it."""

    value: T
    route: Route


@dataclass
class CallBudget:
    """At most ``limit`` provider calls, and ``max_repairs`` repair attempts, for one unit of
    work: every fallback and retry counts. ``used``/``repairs_used`` start from what earlier
    attempts of the same job already spent (``usage.job_calls``).

    Requests the provider turns away before running them (429, 503) don't use ``limit``:
    they cost nothing, and a busy hour shouldn't fail the work (ADR 0008). They have their
    own, wider ``turned_away_limit`` so a long outage still ends."""

    limit: int
    job_id: uuid.UUID | None = None
    used: int = 0
    repairs_used: int = 0
    max_repairs: int = 1
    turned_away: int = 0
    turned_away_limit: int | None = None

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    def check(self) -> None:
        """Raise ``AICallLimitReached`` if no further call is allowed."""
        if self.remaining == 0:
            raise AICallLimitReached(
                f"Stopped after {self.limit} AI calls without a usable answer."
            )
        if self.turned_away_limit is not None and self.turned_away >= self.turned_away_limit:
            raise AICallLimitReached(
                f"The AI providers turned away {self.turned_away} requests (busy or rate limited).",
                busy=True,
            )

    def charge(self, *, turned_away: bool) -> None:
        if turned_away:
            self.turned_away += 1
        else:
            self.used += 1

    @property
    def can_repair(self) -> bool:
        return self.repairs_used < self.max_repairs and self.remaining > 0


@dataclass
class _Pacer:
    """A sliding one-minute window of request times per model (this process only)."""

    sleep: Callable[[float], Awaitable[None]]
    clock: Callable[[], float]
    sent: dict[str, deque[float]] = field(default_factory=dict)

    async def wait_turn(self, key: str, per_minute: int | None) -> None:
        if not per_minute or per_minute <= 0:
            return
        window = self.sent.setdefault(key, deque())
        while True:
            now = self.clock()
            while window and now - window[0] >= PACING_WINDOW_SECONDS:
                window.popleft()
            if len(window) < per_minute:
                window.append(now)
                return
            wait = PACING_WINDOW_SECONDS - (now - window[0])
            log.info("%s: %s requests in the last minute; waiting %.1fs", key, len(window), wait)
            await self.sleep(wait)


@dataclass(frozen=True)
class PingResult:
    route: Route
    latency_ms: int
    reply: str


class _InvalidReply(Exception):
    def __init__(self, reply: str, problem: str) -> None:
        super().__init__(problem)
        self.reply = reply
        self.problem = problem


def json_instruction(schema: type[BaseModel]) -> str:
    return (
        "Reply with one JSON object only, no prose and no code fences. "
        "It must match this JSON Schema:\n" + json.dumps(schema.model_json_schema())
    )


def parse_reply[T: BaseModel](text: str, schema: type[T]) -> T:
    """Validate a reply against ``schema``, tolerating a Markdown code fence around it."""
    stripped = text.strip()
    fenced = _FENCE.match(stripped)
    return schema.model_validate_json(fenced.group(1) if fenced else stripped)


_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,29}$")


def _problem(exc: ValidationError) -> str:
    """A short description of what didn't validate, for the repair prompt and ``detail``.

    For a missing field it also names the keys the object did have (only identifier-like
    keys, so no course text), so the next diagnosis can see e.g. "title" instead of "name".
    """
    errors = exc.errors()
    issues: list[str] = []
    for error in errors:
        if error["type"] == "missing" and isinstance(error.get("input"), dict):
            keys = sorted(k for k in error["input"] if isinstance(k, str) and _KEY.match(k))
            issues.append(f"an object had keys {keys} but no {error['loc'][-1]!r}")
            break
    issues += [
        f"{'.'.join(str(p) for p in error['loc']) or '(root)'}: {error['msg']}"
        for error in errors[:10]
    ]
    return "; ".join(issues)


class LLMClient:
    def __init__(
        self,
        settings: Settings,
        usage: UsageStore,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        now: Callable[[], datetime] = _now,
        jitter: Callable[[], float] = random.random,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings
        self._usage = usage
        self._http = httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(
                settings.ai_read_timeout_seconds, connect=settings.ai_connect_timeout_seconds
            ),
        )
        self._sleep = sleep
        self._now = now
        self._jitter = jitter
        # Route key → when it may be tried again after a 429/5xx (this process only).
        self._cooldown: dict[str, datetime] = {}
        self._pacer = _Pacer(sleep, clock)

    async def aclose(self) -> None:
        await self._http.aclose()

    def routes(self, role: AIRole) -> list[Route]:
        return routes_for(role, self.settings)

    # --- public API ---

    async def complete_text(
        self,
        role: AIRole,
        messages: list[Message],
        *,
        purpose: str,
        user_id: uuid.UUID,
        reasoning_effort: ReasoningEffort | None = None,
    ) -> str:
        """``reasoning_effort`` overrides the routes' configured level for this call."""
        text, _ = await self._complete(
            role,
            messages,
            purpose=purpose,
            user_id=user_id,
            json_mode=False,
            check=None,
            effort=reasoning_effort,
            budget=None,
        )
        return text

    async def complete_json[T: BaseModel](
        self,
        role: AIRole,
        messages: list[Message],
        schema: type[T],
        *,
        purpose: str,
        user_id: uuid.UUID,
        reasoning_effort: ReasoningEffort | None = None,
        budget: CallBudget | None = None,
    ) -> T:
        """Ask for JSON, validate it against ``schema``, and repair it once if needed.

        Raises ``AIInvalidOutput`` if the repaired reply still doesn't validate (or the
        budget allows no repair). ``reasoning_effort`` overrides the routes' level.
        """
        result = await self.complete_json_result(
            role,
            messages,
            schema,
            purpose=purpose,
            user_id=user_id,
            reasoning_effort=reasoning_effort,
            budget=budget,
        )
        return result.value

    async def complete_json_result[T: BaseModel](
        self,
        role: AIRole,
        messages: list[Message],
        schema: type[T],
        *,
        purpose: str,
        user_id: uuid.UUID,
        reasoning_effort: ReasoningEffort | None = None,
        budget: CallBudget | None = None,
    ) -> AIResult[T]:
        """``complete_json``, also saying which provider and model answered."""
        result: list[T] = []

        def check(text: str) -> None:
            try:
                result.append(parse_reply(text, schema))
            except ValidationError as exc:
                raise _InvalidReply(text, _problem(exc)) from exc

        prompt = [system(json_instruction(schema)), *messages]
        try:
            _, route = await self._complete(
                role,
                prompt,
                purpose=purpose,
                user_id=user_id,
                json_mode=True,
                check=check,
                effort=reasoning_effort,
                budget=budget,
            )
            return AIResult(result[-1], route)
        except _InvalidReply as first:
            if budget is not None and not budget.can_repair:
                raise AIInvalidOutput(
                    f"The AI reply for {purpose} didn't match its schema: {first.problem}"
                ) from None
            if budget is not None:
                budget.repairs_used += 1
            log.info("AI reply for %s didn't validate; asking for a repair", purpose)
            repair = [
                *prompt,
                assistant_message(first.reply),
                user(
                    "That reply did not match the schema: "
                    f"{first.problem}. Reply again with the corrected JSON object only."
                ),
            ]
        try:
            _, route = await self._complete(
                role,
                repair,
                purpose=purpose,
                user_id=user_id,
                json_mode=True,
                check=check,
                effort=reasoning_effort,
                budget=budget,
            )
            return AIResult(result[-1], route)
        except _InvalidReply as second:
            raise AIInvalidOutput(
                f"The AI reply for {purpose} didn't match its schema after a repair attempt: "
                f"{second.problem}"
            ) from None

    async def ping(
        self, route: Route, *, user_id: uuid.UUID, limit_seconds: float = PING_TIMEOUT_SECONDS
    ) -> PingResult:
        """One short request to exactly this route (no fallback, no budget). Logged as "ping".

        It thinks as little as the model allows, and gives up after ``limit_seconds``.
        """
        messages = [user("Reply with the single word: pong")]
        started = time.monotonic()
        try:
            completion = await self._adapter(route).complete(
                route.model,
                messages,
                reasoning_effort=route.effort_to_send("minimal"),
                deadline=limit_seconds,
            )
        except ProviderError as exc:
            await self._record(route, "smart", "ping", user_id, started, None, exc)
            raise
        await self._record(route, "smart", "ping", user_id, started, completion, None)
        return PingResult(route, int((time.monotonic() - started) * 1000), completion.text.strip())

    async def list_models(
        self, route: Route, *, limit_seconds: float = PING_TIMEOUT_SECONDS
    ) -> list[str]:
        return await self._adapter(route).list_models(deadline=limit_seconds)

    # --- internals ---

    def _adapter(self, route: Route) -> OpenAICompatAdapter:
        return OpenAICompatAdapter(route.provider, self._http)

    async def _record(
        self,
        route: Route,
        role: AIRole,
        purpose: str,
        user_id: uuid.UUID,
        started: float,
        completion: Completion | None,
        error: ProviderError | None,
        *,
        invalid: str | None = None,
        budget: CallBudget | None = None,
    ) -> None:
        """One ``ai_usage`` row. ``detail`` says why it failed, never what was said."""
        detail: str | None = None
        if error is not None:
            detail = str(error)
            if error.timed_out:
                outcome = "timeout"
            elif error.rate_limited:
                outcome = "rate_limited"
            elif error.overloaded:
                outcome = "overloaded"
            else:
                outcome = "error"
        elif completion is not None and completion.truncated:
            outcome, detail = "truncated", f"finish_reason {completion.finish_reason}"
        elif completion is not None and completion.refused:
            outcome, detail = "refused", completion.refusal
        elif invalid is not None:
            outcome, detail = "invalid_json", invalid
        else:
            outcome = "ok"
        await self._usage.record(
            UsageRecord(
                user_id=user_id,
                provider=route.provider.name,
                model=route.model,
                role=role,
                purpose=purpose[:50],
                input_tokens=completion.input_tokens if completion else 0,
                output_tokens=completion.output_tokens if completion else 0,
                latency_ms=int((time.monotonic() - started) * 1000),
                outcome=outcome,
                job_id=budget.job_id if budget else None,
                detail=detail,
            )
        )

    async def _budget_reset(self, route: Route, user_id: uuid.UUID) -> datetime | None:
        """When the route's budget resets if it's used up today, else None."""
        if route.daily_budget is None:
            return None
        now = self._now()
        zone = quota_zone(route.provider.name, self.settings)
        used = await self._usage.count_since(
            user_id=user_id,
            provider=route.provider.name,
            model=route.model,
            since=window_start(now, zone),
        )
        return next_reset(now, zone) if used >= route.daily_budget else None

    def _delay(self, error: ProviderError, attempt: int) -> float:
        """Seconds before retrying: Retry-After when given, else exponential backoff."""
        if error.retry_after is not None:
            return error.retry_after
        return float(BACKOFF_BASE_SECONDS * 2**attempt)

    async def _complete(
        self,
        role: AIRole,
        messages: list[Message],
        *,
        purpose: str,
        user_id: uuid.UUID,
        json_mode: bool,
        check: Callable[[str], None] | None,
        effort: ReasoningEffort | None,
        budget: CallBudget | None,
    ) -> tuple[str, Route]:
        if has_images(messages):
            # Only the vision role's models read images, whatever role was asked for.
            role = "vision"
        routes = [route for route in self.routes(role) if route.configured]
        if not routes:
            if role == "vision" and any(r.configured for r in self.routes("smart")):
                raise AIUnavailable(
                    "No configured model can read images. Add a key for a provider in AI_VISION "
                    "(GEMINI_API_KEY or GROQ_API_KEY) to apps/api/.env.",
                    retry_at=None,
                )
            raise AIUnavailable(NOT_CONFIGURED, retry_at=None)

        waits: list[datetime] = []
        refusals: list[str] = []
        for route in routes:
            blocked = self._cooldown.get(route.key)
            if blocked is not None and blocked > self._now():
                waits.append(blocked)
                continue
            reset = await self._budget_reset(route, user_id)
            if reset is not None:
                log.info("%s: daily budget used up until %s", route.key, reset.isoformat())
                waits.append(reset)
                continue

            attempt = 0
            while True:
                if budget is not None:
                    budget.check()
                await self._pacer.wait_turn(
                    route.key, self.settings.ai_requests_per_minute.get(route.key)
                )
                started = time.monotonic()
                try:
                    completion = await self._adapter(route).complete(
                        route.model,
                        messages,
                        json_mode=json_mode,
                        reasoning_effort=route.effort_to_send(effort),
                    )
                except ProviderError as exc:
                    if budget is not None:
                        budget.charge(turned_away=exc.turned_away)
                    await self._record(
                        route, role, purpose, user_id, started, None, exc, budget=budget
                    )
                    log.warning("%s failed (%s) for %s", route.key, exc, purpose)
                    delay = self._delay(exc, attempt)
                    if (exc.rate_limited or (exc.status or 0) >= 500) and (
                        attempt < self.settings.ai_retries
                        and delay <= self.settings.ai_max_wait_seconds
                    ):
                        attempt += 1
                        await self._sleep(delay + self._jitter() * max(1.0, delay / 2))
                        continue
                    until = self._now() + max(timedelta(seconds=delay), DEFAULT_COOLDOWN)
                    if exc.turned_away or exc.timed_out or exc.status in (None, 413):
                        # This model can't take it now: the next one may.
                        self._cooldown[route.key] = until
                        waits.append(until)
                        break
                    if (exc.status or 0) >= 500:
                        self._cooldown[route.key] = until
                        raise AIUnavailable(
                            f"{route.key} is having problems ({exc}). Trying again after "
                            f"{until.astimezone(UTC):%Y-%m-%d %H:%M} UTC.",
                            retry_at=until,
                        ) from exc
                    raise AIRequestFailed(str(exc)) from exc
                if budget is not None:
                    budget.charge(turned_away=False)
                self._cooldown.pop(route.key, None)
                if completion.refused:
                    # This model won't answer this content; another may. No repair is spent.
                    await self._record(
                        route, role, purpose, user_id, started, completion, None, budget=budget
                    )
                    log.warning("%s declined %s (%s)", route.key, purpose, completion.refusal)
                    refusals.append(f"{route.key}: {completion.refusal}")
                    break
                if completion.truncated:
                    await self._record(
                        route, role, purpose, user_id, started, completion, None, budget=budget
                    )
                    raise AITruncated(f"{route.key}: the reply was cut off at its output limit")
                if check is not None:
                    try:
                        check(completion.text)
                    except _InvalidReply as invalid:
                        await self._record(
                            route,
                            role,
                            purpose,
                            user_id,
                            started,
                            completion,
                            None,
                            invalid=invalid.problem,
                            budget=budget,
                        )
                        raise
                await self._record(
                    route, role, purpose, user_id, started, completion, None, budget=budget
                )
                return completion.text, route

        if refusals and not waits:
            raise AIRefused(
                "Every AI model declined to answer for this content (" + "; ".join(refusals) + ")."
            )
        retry_at = min(waits) if waits else self._now() + ERROR_RETRY
        raise AIUnavailable(
            f"The AI providers can't take this request now (rate limits or daily quotas). "
            f"Trying again after {retry_at.astimezone(UTC):%Y-%m-%d %H:%M} UTC.",
            retry_at=retry_at,
        )


_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """The process's client, built from settings on first use."""
    global _client
    if _client is None:
        from app.ai.usage import DbUsageStore
        from app.core.config import get_settings
        from app.core.db import get_sessionmaker

        _client = LLMClient(get_settings(), DbUsageStore(get_sessionmaker()))
    return _client


def set_llm_client(client: LLMClient | None) -> None:
    """Replace the process's client (tests install one with a fake transport)."""
    global _client
    _client = client
