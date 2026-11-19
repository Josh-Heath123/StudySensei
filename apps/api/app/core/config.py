from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]

ReasoningEffort = Literal["minimal", "low", "medium", "high"]


class RouteSetting(BaseModel):
    """One model in a role: ``"provider/model"`` and how hard it should think.

    ``reasoning_effort`` is sent only to models listed in ``ai_reasoning_efforts``, raised
    to the model's lowest supported level if needed; empty means don't send it, so the
    model uses its own default. A plain string in the
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
    # Load the embedding model when the API and the worker start, rather than on the first
    # search (about 1.4 s, 19 Nov 2026). The API loads it in the background.
    preload_embedder: bool = True

    # --- AI providers (decision 0002, ARCHITECTURE "AI integration") ---
    # A provider without a key is skipped. Keys are secrets: never log or return them.
    gemini_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    ollama_base_url: str = "http://localhost:11434/v1"
    # Ollama is off unless a model is named; it's then tried last in every role, with no budget.
    ollama_model: str | None = None
    # Each role is an ordered list of routes, tried first to last (ADR 0002, 2026-11-17 update).
    # Ordered by free-tier daily limits and latency: gemini-3.8-flash allows ~20 requests a
    # day and has timed out at 30 s, so it's only the last resort; Flash-Lite (~500 a day,
    # 1-10 s) and Groq's gpt-oss (~1,000 a day) carry the load.
    ai_smart: list[RouteSetting] = _routes(
        "low",
        "groq/openai/gpt-oss-120b",
        "gemini/gemini-3.5-flash-lite",
        "gemini/gemini-3.8-flash",
    )
    ai_bulk: list[RouteSetting] = [
        RouteSetting(route="gemini/gemini-3.5-flash-lite", reasoning_effort="minimal"),
        RouteSetting(route="groq/openai/gpt-oss-20b", reasoning_effort="low"),
    ]
    # Any request with an image goes here instead of its own role (scanned pages, figure
    # slides). Every model listed must accept images; gpt-oss is text-only. Ollama isn't
    # added, since a local model may not read images.
    ai_vision: list[RouteSetting] = _routes(
        "low",
        "gemini/gemini-3.5-flash-lite",
        "groq/qwen/qwen3.8-27b",
        "gemini/gemini-3.8-flash",
    )
    # Whole documents in one prompt (topic maps: every page of a material, or every
    # material's proposal for the merge). Flash-Lite leads: a 1M-token context and ~500
    # requests a day. Groq is last: its free tier allows 8K tokens a minute and 200K a day,
    # so a whole deck would use a big share of the day (ADR 0006).
    ai_long: list[RouteSetting] = _routes(
        "low",
        "gemini/gemini-3.5-flash-lite",
        "gemini/gemini-3.8-flash",
        "groq/openai/gpt-oss-120b",
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
    # Requests per minute per "provider/model": the free-tier RPM less a margin. The client
    # waits its turn rather than collecting 429s (ADR 0007). Missing means no pacing.
    ai_requests_per_minute: dict[str, int] = {
        "gemini/gemini-3.8-flash": 4,  # free tier 5/min
        "gemini/gemini-3.5-flash-lite": 12,  # free tier 15/min
        "groq/openai/gpt-oss-120b": 25,  # free tier 30/min
        "groq/openai/gpt-oss-20b": 25,  # free tier 30/min
        "groq/qwen/qwen3.8-27b": 25,  # free tier 30/min
    }
    # The reasoning_effort levels each "provider/model" accepts, from its docs (2026-11-17):
    # Gemini's thinking page, Groq's reasoning page. A level a model lacks is raised to its
    # lowest supported one (minimal → low on 3.8 Flash); a model not listed is sent none.
    ai_reasoning_efforts: dict[str, list[ReasoningEffort]] = {
        "gemini/gemini-3.8-flash": ["low", "medium", "high"],  # no minimal; medium is default
        "gemini/gemini-3.5-flash-lite": ["minimal", "low", "medium", "high"],
        "groq/openai/gpt-oss-120b": ["low", "medium", "high"],
        "groq/openai/gpt-oss-20b": ["low", "medium", "high"],
        "groq/qwen/qwen3.8-27b": ["low", "medium", "high"],  # also its own none/default
    }
    # When each provider's daily quota resets (midnight in this time zone).
    ai_quota_timezone: dict[str, str] = {"gemini": "America/Los_Angeles", "groq": "UTC"}
    # Topic maps (ADR 0006). A material's text beyond this many characters is cut off
    # (about 100K tokens: a long textbook still fits Flash-Lite with room to answer).
    topic_max_chars: int = 400_000
    # A material longer than this many pages is analysed in parts of about this size, so
    # each reply stays well inside the output limit; the parts' topics are combined.
    topic_part_pages: int = 40
    # Provider calls one material may use per run, counting fallbacks, the one repair and
    # job retries (ADR 0007). Parts are sized so a material fits with one call to spare.
    topic_max_calls: int = 4
    # Requests turned away before running (429, 503 "high demand") don't use that cap: they
    # cost nothing. This wider cap ends a run during a long outage instead (ADR 0008).
    topic_max_turned_away: int = 20
    # The merge request's size, in estimated tokens (system prompt, JSON instruction and
    # prompt). Descriptions are added only while it fits, so Groq (8K tokens a minute on the
    # free tier) can take it when Gemini can't (ADR 0009).
    topic_merge_max_tokens: int = 7000
    # A chunk links to a topic by similarity when the cosine of the topic's "name:
    # description" and the chunk is at least this, keeping at most this many per topic.
    # First calibrated at 0.63 with bge-small on tests/topic_maps/linking_fixtures.py
    # (teaching passages 0.63-0.90, others 0.41-0.62). On COS330 (evals/linking, 18 Nov
    # 2026) 0.63 never cut: every similarity link scored 0.67-0.88. 0.75 kept 88 % of the
    # same-chapter links and 48 % of the cross-chapter ones; migration 0016 relinks.
    topic_link_threshold: float = 0.75
    topic_link_max_chunks: int = 12
    # Pages with less extracted text than this (title slides, "Chapter N" dividers,
    # caption-only figure slides) are never similarity candidates; cited pages still link.
    # COS330, 18 Nov 2026: 127 of 318 similarity links were such pages, 77 across chapters.
    topic_link_min_page_chars: int = 150
    # --- Tutor retrieval (Phase 3; ARCHITECTURE "Search" and "Tutor") ---
    # Chunks linked to the session's current topic (or its subtopics) have their fused RRF
    # score multiplied by this; 1.0 turns the boost off. COS330 (evals/search --retrieval,
    # 18 Nov 2026): x1.25 to x2 each brought 32 acceptable pages into the 8 sources (30 with
    # no boost); with a topic from another chapter, x1.25 kept the right page at S1 for 11 of
    # 15 queries and x1.5 or more for only 9.
    tutor_topic_boost: float = 1.25
    # The sources' share of a tutor request, in estimated tokens (3.5 characters a token,
    # app/services/tutor/prompts.py). Sized for Groq's 8,000 tokens a minute on the smart
    # role: 4,500 for sources + about 600 for the prompts and question + 2,000 for the answer.
    tutor_context_max_tokens: int = 4500
    # Connecting gives up quickly; reading allows for a long answer (and thinking) to arrive.
    ai_connect_timeout_seconds: float = 10.0
    ai_read_timeout_seconds: float = 90.0
    # Retries of one model after a 429/5xx before falling through to the next.
    ai_retries: int = 1
    # A Retry-After longer than this isn't waited for: the next model is tried instead.
    ai_max_wait_seconds: float = 20.0

    @field_validator("ai_smart", "ai_bulk", "ai_vision", "ai_long", mode="before")
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
