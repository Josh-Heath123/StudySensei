"""Schemas for the AI status endpoint. Keys are only ever reported as set or not."""

from datetime import datetime
from typing import Literal

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
    # In the vision role, which takes every request that includes an image.
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


class AIPingResult(BaseModel):
    provider: str
    model: str
    # ok: it answered. failed: see ``error``. skipped: its daily budget is used up, so it
    # wasn't called (see ``resets_at``).
    status: Literal["ok", "failed", "skipped"]
    latency_ms: int | None
    # The provider's own error text (never a key or the prompt).
    error: str | None
    resets_at: datetime | None
    # Whether the model is in the provider's /models list; null when that list failed.
    in_models_list: bool | None
    models_list_error: str | None


class AIPingOut(BaseModel):
    # One per configured model, in role order; empty when no provider is configured.
    results: list[AIPingResult]
