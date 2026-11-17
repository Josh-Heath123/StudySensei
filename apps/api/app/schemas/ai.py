"""Schemas for the AI status endpoint. Keys are only ever reported as set or not."""

from datetime import datetime

from pydantic import BaseModel


class AIProviderStatus(BaseModel):
    name: str
    # Gemini/Groq: an API key is set. Ollama: OLLAMA_MODEL is set (it needs no key).
    configured: bool
    key_set: bool


class AIModelStatus(BaseModel):
    provider: str
    model: str
    configured: bool
    vision: bool
    # Requests the client allows itself per day (the free tier less a margin); null = no limit.
    daily_budget: int | None
    # This user's requests counted against the budget since the quota last reset.
    used_today: int
    resets_at: datetime | None


class AIStatusOut(BaseModel):
    # At least one provider is configured, so AI features can run.
    available: bool
    providers: list[AIProviderStatus]
    # Role → its models, in the order they're tried.
    roles: dict[str, list[str]]
    models: list[AIModelStatus]
