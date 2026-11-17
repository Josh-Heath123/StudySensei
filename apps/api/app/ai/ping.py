"""Check the AI keys work: ``uv run python -m app.ai.ping``.

For every configured model in every role it sends a one-line prompt and prints the
provider, model, latency and reply. It also checks each model ID is in the provider's
/models list. Calls are logged in ai_usage (purpose "ping") against the local user.
Keys are never printed.
"""

import asyncio
import sys

from sqlalchemy import select

from app.ai.adapter import ProviderError
from app.ai.client import LLMClient
from app.ai.routes import ROLES, all_routes, routes_for
from app.ai.usage import DbUsageStore
from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.models import User


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
    failures = 0
    listed: dict[str, list[str] | str] = {}
    try:
        for route in routes:
            name = route.provider.name
            if name not in listed:
                try:
                    listed[name] = await client.list_models(route)
                except ProviderError as exc:
                    listed[name] = str(exc)
            models = listed[name]
            if isinstance(models, str):
                in_list = f"/models failed: {models}"
            else:
                in_list = "in /models" if route.model in models else "NOT in /models"
            try:
                result = await client.ping(route, user_id=user.id)
            except ProviderError as exc:
                failures += 1
                print(f"FAIL  {name:7} {route.model:28} {in_list:16} {exc}")
                continue
            reply = result.reply.replace("\n", " ")[:60]
            print(f"ok    {name:7} {route.model:28} {in_list:16} {result.latency_ms:6} ms  {reply}")
    finally:
        await client.aclose()
        await get_engine().dispose()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
