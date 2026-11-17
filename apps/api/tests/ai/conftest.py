from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LLMClient
from app.ai.usage import DbUsageStore, SessionFactory
from app.core.config import ReasoningEffort, RouteSetting, Settings, get_settings
from tests.fakes import FakeLLM

# Fake keys: the fake transport is the only thing that ever sees them.
GEMINI_KEY = "gemini-test-key-0000"
GROQ_KEY = "groq-test-key-0000"
# The client's clock. Real time, because the usage rows it writes get the database's now().
NOW = datetime.now(UTC)


def routes(*keys: str, effort: ReasoningEffort | None = None) -> list[RouteSetting]:
    """Route settings for ``model_copy`` (which, unlike the env, doesn't parse plain strings)."""
    return [RouteSetting(route=key, reasoning_effort=effort) for key in keys]


@pytest.fixture
def settings() -> Settings:
    """Two providers, small budgets, models with short test names."""
    return get_settings().model_copy(
        update={
            "gemini_api_key": SecretStr(GEMINI_KEY),
            "groq_api_key": SecretStr(GROQ_KEY),
            "ollama_model": None,
            # No effort here; test_reasoning.py covers it with real-shaped model IDs.
            "ai_smart": routes("gemini/flash", "groq/oss-120b"),
            "ai_bulk": routes("gemini/flash-lite", "groq/oss-20b"),
            "ai_daily_budget": {"gemini/flash": 3, "groq/oss-120b": 5, "gemini/flash-lite": 10},
            # The only image reader in these tests (vision tests add a second).
            "ai_vision": routes("gemini/flash"),
            "ai_retries": 1,
            "ai_max_wait_seconds": 20.0,
        }
    )


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def usage_sessions(session: AsyncSession) -> SessionFactory:
    @asynccontextmanager
    async def factory() -> AsyncIterator[AsyncSession]:
        yield session

    return factory


class Sleeps:
    """Records the client's waits instead of waiting."""

    def __init__(self) -> None:
        self.seconds: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.seconds.append(seconds)


@pytest.fixture
def sleeps() -> Sleeps:
    return Sleeps()


MakeClient = Callable[..., LLMClient]


@pytest.fixture
def make_client(
    settings: Settings, fake_llm: FakeLLM, usage_sessions: SessionFactory, sleeps: Sleeps
) -> MakeClient:
    def make(now: datetime = NOW, **changes: object) -> LLMClient:
        return LLMClient(
            settings.model_copy(update=changes) if changes else settings,
            DbUsageStore(usage_sessions),
            transport=fake_llm.transport,
            sleep=sleeps,
            now=lambda: now,
            jitter=lambda: 0.0,
        )

    return make
