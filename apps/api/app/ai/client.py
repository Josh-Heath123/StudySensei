"""The LLM client: roles, fallback, backoff, daily budgets and usage logging (decision 0002).

    client = get_llm_client()
    text = await client.complete_text("smart", [system(...), user(...)],
                                      purpose="tutor", user_id=user.id)
    topics = await client.complete_json("smart", messages, TopicMap,
                                        purpose="topic_extraction", user_id=user.id)

For each request it walks the role's routes in order and skips a route that is:
- on a provider without a key,
- unable to read images when the messages have one,
- cooling down after a 429 or 5xx, or
- out of its daily budget (counted from ``ai_usage`` since the provider's quota reset).

A 429 or 5xx is retried on the same model after its Retry-After (or a jittered backoff)
when that's short, and otherwise falls through to the next route. When every route is out,
``AIUnavailable`` says when to try again. Every request is logged in ``ai_usage``.

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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from pydantic import BaseModel, ValidationError

from app.ai.adapter import Completion, OpenAICompatAdapter, ProviderError
from app.ai.budget import next_reset, quota_zone, window_start
from app.ai.errors import NOT_CONFIGURED, AIInvalidOutput, AIUnavailable
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
_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def _now() -> datetime:
    return datetime.now(UTC)


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


def _problem(exc: ValidationError) -> str:
    """A short description of what didn't validate, for the repair prompt."""
    issues = [
        f"{'.'.join(str(p) for p in error['loc']) or '(root)'}: {error['msg']}"
        for error in exc.errors()[:10]
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
        return await self._complete(
            role,
            messages,
            purpose=purpose,
            user_id=user_id,
            json_mode=False,
            check=None,
            effort=reasoning_effort,
        )

    async def complete_json[T: BaseModel](
        self,
        role: AIRole,
        messages: list[Message],
        schema: type[T],
        *,
        purpose: str,
        user_id: uuid.UUID,
        reasoning_effort: ReasoningEffort | None = None,
    ) -> T:
        """Ask for JSON, validate it against ``schema``, and repair it once if needed.

        Raises ``AIInvalidOutput`` if the repaired reply still doesn't validate.
        ``reasoning_effort`` overrides the routes' configured level for this call.
        """
        result: list[T] = []

        def check(text: str) -> None:
            try:
                result.append(parse_reply(text, schema))
            except ValidationError as exc:
                raise _InvalidReply(text, _problem(exc)) from exc

        prompt = [system(json_instruction(schema)), *messages]
        try:
            await self._complete(
                role,
                prompt,
                purpose=purpose,
                user_id=user_id,
                json_mode=True,
                check=check,
                effort=reasoning_effort,
            )
            return result[-1]
        except _InvalidReply as first:
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
            await self._complete(
                role,
                repair,
                purpose=purpose,
                user_id=user_id,
                json_mode=True,
                check=check,
                effort=reasoning_effort,
            )
            return result[-1]
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
        invalid: bool = False,
    ) -> None:
        if error is not None:
            if error.timed_out:
                outcome = "timeout"
            else:
                outcome = "rate_limited" if error.rate_limited else "error"
        else:
            outcome = "invalid_json" if invalid else "ok"
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
    ) -> str:
        routes = [route for route in self.routes(role) if route.configured]
        if not routes:
            raise AIUnavailable(NOT_CONFIGURED, retry_at=None)
        if has_images(messages):
            routes = [route for route in routes if route.vision]
            if not routes:
                raise AIUnavailable(
                    f"No configured {role} model can read images. "
                    "Add GEMINI_API_KEY to apps/api/.env.",
                    retry_at=None,
                )

        waits: list[datetime] = []
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
                started = time.monotonic()
                try:
                    completion = await self._adapter(route).complete(
                        route.model,
                        messages,
                        json_mode=json_mode,
                        reasoning_effort=route.effort_to_send(effort),
                    )
                except ProviderError as exc:
                    await self._record(route, role, purpose, user_id, started, None, exc)
                    log.warning("%s failed (%s) for %s", route.key, exc, purpose)
                    if not exc.retryable:
                        break  # a bad key or unknown model: the next route might work
                    delay = self._delay(exc, attempt)
                    if (
                        attempt < self.settings.ai_retries
                        and delay <= self.settings.ai_max_wait_seconds
                    ):
                        attempt += 1
                        await self._sleep(delay + self._jitter() * max(1.0, delay / 2))
                        continue
                    until = self._now() + max(timedelta(seconds=delay), DEFAULT_COOLDOWN)
                    self._cooldown[route.key] = until
                    waits.append(until)
                    break
                self._cooldown.pop(route.key, None)
                if check is not None:
                    try:
                        check(completion.text)
                    except _InvalidReply:
                        await self._record(
                            route, role, purpose, user_id, started, completion, None, invalid=True
                        )
                        raise
                await self._record(route, role, purpose, user_id, started, completion, None)
                return completion.text

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
