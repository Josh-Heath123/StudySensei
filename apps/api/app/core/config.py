from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]

ReasoningEffort = Literal["minimal", "low", "medium", "high"]


class RouteSetting(BaseModel):
    """One model in a role: ``"provider/model"`` and how hard it should think.

    ``reasoning_effort`` is sent only to providers that accept it (Gemini, Groq's gpt-oss);
    empty means don't send it, so the model uses its own default. A plain string in the
    env (``"gemini/gemini-3.8-flash"``) means no effort.
    """

    route: str
    reasoning_effort: ReasoningEffort | None = None

    @field_validator("reasoning_effort", mode="before")
    @classmethod
    def _blank_is_default(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value


def _routes(effort: ReasoningEffort | None, *keys: str) -> list[RouteSetting]:
    return [RouteSetting(route=key, reasoning_effort=effort) for key in keys]


class Settings(BaseSettings):
    """App settings, read from environment variables or apps/api/.env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://studysensei:studysensei@localhost:5433/studysensei"
    # Origins allowed to call the API from a browser (the Vite dev server).
    cors_origins: list[str] = ["http://localhost:5173"]
    # How long /health waits for the database before reporting it as down.
    health_db_timeout_seconds: float = 2.0
    local_user_email: str = "local@studysensei.dev"
    # Uploaded materials (gitignored). Blobs are keyed {user_id}/{sha256}.
    storage_dir: Path = REPO_ROOT / "data" / "materials"
    # The local embedding model's download cache (gitignored).
    models_dir: Path = REPO_ROOT / "data" / "models"
    max_upload_bytes: int = 50 * 1024 * 1024
    # How long the job worker sleeps when the queue is empty.
    worker_poll_seconds: float = 1.0

    # --- AI providers (decision 0002, ARCHITECTURE "AI integration") ---
    # A provider without a key is skipped. Keys are secrets: never log or return them.
    gemini_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    ollama_base_url: str = "http://localhost:11434/v1"
    # Ollama is off unless a model is named; it's then tried last in every role, with no budget.
    ollama_model: str | None = None
    # Each role is an ordered list of routes, tried first to last. Gemini 3 always thinks
    # (at its default level unless told); bulk work needs little, smart work a bit more.
    ai_smart: list[RouteSetting] = _routes(
        "low", "gemini/gemini-3.8-flash", "groq/openai/gpt-oss-120b", "groq/qwen/qwen3.8-27b"
    )
    ai_bulk: list[RouteSetting] = _routes(
        "minimal", "gemini/gemini-3.5-flash-lite", "groq/openai/gpt-oss-20b"
    )
    # Requests per day per "provider/model": the free-tier limit less about 10 %.
    # A model missing here has no daily budget.
    ai_daily_budget: dict[str, int] = {
        "gemini/gemini-3.8-flash": 18,  # free tier 20/day
        "gemini/gemini-3.5-flash-lite": 450,  # free tier 500/day
        "groq/openai/gpt-oss-120b": 900,  # free tier 1,000/day
        "groq/openai/gpt-oss-20b": 900,  # free tier 1,000/day
        "groq/qwen/qwen3.8-27b": 900,  # free tier 1,000/day
    }
    # Models that accept images; a request with an image skips the others.
    ai_vision_models: list[str] = [
        "gemini/gemini-3.8-flash",
        "gemini/gemini-3.5-flash-lite",
        "groq/qwen/qwen3.8-27b",
    ]
    # When each provider's daily quota resets (midnight in this time zone).
    ai_quota_timezone: dict[str, str] = {"gemini": "America/Los_Angeles", "groq": "UTC"}
    # Connecting gives up quickly; reading allows for a long answer (and thinking) to arrive.
    ai_connect_timeout_seconds: float = 10.0
    ai_read_timeout_seconds: float = 90.0
    # Retries of one model after a 429/5xx before falling through to the next.
    ai_retries: int = 1
    # A Retry-After longer than this isn't waited for: the next model is tried instead.
    ai_max_wait_seconds: float = 20.0

    @field_validator("ai_smart", "ai_bulk", mode="before")
    @classmethod
    def _plain_route_strings(cls, value: object) -> object:
        """Allow ``["gemini/gemini-3.8-flash", …]`` as well as route objects."""
        if isinstance(value, list):
            return [{"route": item} if isinstance(item, str) else item for item in value]
        return value

    @field_validator("gemini_api_key", "groq_api_key", "ollama_model", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        """``GEMINI_API_KEY=`` in .env means no key."""
        return None if isinstance(value, str) and not value.strip() else value


@lru_cache
def get_settings() -> Settings:
    return Settings()
