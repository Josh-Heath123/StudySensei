"""Check the AI keys work: ``uv run python -m app.ai.ping``.

For every configured model in every role it prints ``→ provider/model …`` and, once the
call returns, ``ok`` with the latency and reply or ``FAIL`` with the reason. Each call
thinks as little as the model allows and has its own 30 s limit, so one slow model
can't stall the rest. It also checks each model ID is in the provider's /models list.
Calls are logged in ai_usage (purpose "ping") against the local user. Keys are never printed.
"""

import asyncio
import io
import sys
import time
import uuid
from typing import TextIO

from sqlalchemy import select

from app.ai.adapter import ProviderError
from app.ai.client import PING_TIMEOUT_SECONDS, LLMClient
from app.ai.routes import ROLES, Route, all_routes, routes_for
from app.ai.usage import DbUsageStore
from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.models import User


async def run_pings(
    client: LLMClient,
    routes: list[Route],
    *,
    user_id: uuid.UUID,
    out: TextIO,
    limit_seconds: float = PING_TIMEOUT_SECONDS,
) -> int:
    """Ping each route in turn, writing progress to ``out`` as it goes. Returns the failures."""
    failures = 0
    listed: dict[str, list[str] | str] = {}
    for route in routes:
        out.write(f"→ {route.key} … ")
        out.flush()
        name = route.provider.name
        if name not in listed:
            try:
                listed[name] = await client.list_models(route, limit_seconds=limit_seconds)
            except ProviderError as exc:
                listed[name] = str(exc)
        models = listed[name]
        if isinstance(models, str):
            in_list = f"(/models failed: {models})"
        else:
            in_list = "" if route.model in models else "(NOT in /models)"
        started = time.monotonic()
        try:
            result = await client.ping(route, user_id=user_id, limit_seconds=limit_seconds)
        except Exception as exc:  # report it and carry on with the next model
            failures += 1
            seconds = time.monotonic() - started
            reason = str(exc) if isinstance(exc, ProviderError) else type(exc).__name__
            out.write(f"FAIL after {seconds:.1f} s: {reason} {in_list}".rstrip() + "\n")
        else:
            reply = result.reply.replace("\n", " ")[:60]
            out.write(f"ok {result.latency_ms} ms: {reply} {in_list}".rstrip() + "\n")
        out.flush()
    return failures


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
