"""Check the AI keys work: ``uv run python -m app.ai.ping`` (and ``POST /ai/ping``).

``ping_routes`` tests every given model at once and returns one ``PingOutcome`` each, in
the order given. Each call thinks as little as the model allows and has its own 30 s
limit, so one slow model can't stall the rest. A model whose daily budget is used up
isn't called. It also checks each model ID is in the provider's /models list.
Calls are logged in ai_usage (purpose "ping") against the given user. Keys never appear.

The CLI prints ``→ provider/model …`` and then ``ok`` with the latency and reply, ``FAIL``
with the reason, or ``skipped`` when the budget is used up.
"""

import asyncio
import io
import sys
import time
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Literal, TextIO

from sqlalchemy import select

from app.ai.adapter import ProviderError
from app.ai.client import PING_TIMEOUT_SECONDS, LLMClient
from app.ai.routes import ROLES, Route, all_routes, routes_for
from app.ai.usage import DbUsageStore
from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.models import User

PingStatus = Literal["ok", "failed", "skipped"]


@dataclass(frozen=True)
class PingOutcome:
    route: Route
    status: PingStatus
    # How long the call took (ok or failed); None when it was skipped.
    latency_ms: int | None = None
    reply: str = ""
    # Why it failed: the provider's own error text (never a key), or the exception type.
    error: str | None = None
    # Skipped: when the daily budget resets.
    resets_at: datetime | None = None
    # Whether the model is in the provider's /models list; None if that list failed.
    listed: bool | None = None
    list_error: str | None = None


async def _list_models(client: LLMClient, route: Route, limit_seconds: float) -> list[str] | str:
    """The provider's model IDs, or the reason the list failed."""
    try:
        return await client.list_models(route, limit_seconds=limit_seconds)
    except ProviderError as exc:
        return str(exc)


async def _ping_one(
    client: LLMClient, route: Route, *, user_id: uuid.UUID, limit_seconds: float
) -> PingOutcome:
    reset = await client.budget_reset(route, user_id)
    if reset is not None:
        return PingOutcome(route, "skipped", resets_at=reset)
    started = time.monotonic()
    try:
        result = await client.ping(route, user_id=user_id, limit_seconds=limit_seconds)
    except Exception as exc:  # report it; the other models carry on
        reason = str(exc) if isinstance(exc, ProviderError) else type(exc).__name__
        latency = int((time.monotonic() - started) * 1000)
        return PingOutcome(route, "failed", latency_ms=latency, error=reason)
    return PingOutcome(route, "ok", latency_ms=result.latency_ms, reply=result.reply)


async def ping_routes(
    client: LLMClient,
    routes: list[Route],
    *,
    user_id: uuid.UUID,
    limit_seconds: float = PING_TIMEOUT_SECONDS,
) -> list[PingOutcome]:
    """Ping every route concurrently (one request each) and list each provider's models."""
    providers = {route.provider.name: route for route in routes}
    lists, outcomes = await asyncio.gather(
        asyncio.gather(*(_list_models(client, r, limit_seconds) for r in providers.values())),
        asyncio.gather(
            *(_ping_one(client, r, user_id=user_id, limit_seconds=limit_seconds) for r in routes)
        ),
    )
    listed = dict(zip(providers, lists, strict=True))
    results = []
    for outcome in outcomes:
        models = listed[outcome.route.provider.name]
        if isinstance(models, str):
            results.append(replace(outcome, listed=None, list_error=models))
        else:
            results.append(replace(outcome, listed=outcome.route.model in models))
    return results


def format_outcome(outcome: PingOutcome) -> str:
    """One CLI line: ``→ gemini/flash … ok 812 ms: pong``."""
    if outcome.listed is None:
        in_list = f"(/models failed: {outcome.list_error})"
    else:
        in_list = "" if outcome.listed else "(NOT in /models)"
    if outcome.status == "skipped":
        until = outcome.resets_at.astimezone(UTC) if outcome.resets_at else None
        result = f"skipped: budget used up until {until:%Y-%m-%d %H:%M} UTC"
    elif outcome.status == "failed":
        seconds = (outcome.latency_ms or 0) / 1000
        result = f"FAIL after {seconds:.1f} s: {outcome.error}"
    else:
        reply = outcome.reply.replace("\n", " ")[:60]
        result = f"ok {outcome.latency_ms} ms: {reply}"
    return f"→ {outcome.route.key} … {result} {in_list}".rstrip()


async def run_pings(
    client: LLMClient,
    routes: list[Route],
    *,
    user_id: uuid.UUID,
    out: TextIO,
    limit_seconds: float = PING_TIMEOUT_SECONDS,
) -> int:
    """Ping the routes and write one line each to ``out``. Returns the failures."""
    outcomes = await ping_routes(client, routes, user_id=user_id, limit_seconds=limit_seconds)
    for outcome in outcomes:
        out.write(format_outcome(outcome) + "\n")
    out.flush()
    return sum(1 for outcome in outcomes if outcome.status == "failed")


async def main() -> int:
    settings = get_settings()
    sessions = get_sessionmaker()
    async with sessions() as session:
        user = await session.scalar(select(User).where(User.email == settings.local_user_email))
    if user is None:
        print("Local user not found. Run `npm run db:seed` first.")
        return 1

    for role in ROLES:
        print(f"{role}: {' -> '.join(r.key for r in routes_for(role, settings))}")
    routes = [route for route in all_routes(settings) if route.configured]
    skipped = [route.key for route in all_routes(settings) if not route.configured]
    if skipped:
        print(f"Skipped (no key): {', '.join(skipped)}")
    if not routes:
        print("No AI provider is configured. Add GEMINI_API_KEY or GROQ_API_KEY to apps/api/.env.")
        return 1

    client = LLMClient(settings, DbUsageStore(sessions))
    try:
        failures = await run_pings(client, routes, user_id=user.id, out=sys.stdout)
    finally:
        await client.aclose()
        await get_engine().dispose()
    return 1 if failures else 0


if __name__ == "__main__":
    # "→" and "…" on a Windows console or pipe whose code page lacks them.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(asyncio.run(main()))
