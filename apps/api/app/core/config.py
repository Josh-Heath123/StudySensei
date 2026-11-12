from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings, read from environment variables or apps/api/.env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://studysensei:studysensei@localhost:5433/studysensei"
    # Origins allowed to call the API from a browser (the Vite dev server).
    cors_origins: list[str] = ["http://localhost:5173"]
    # How long /health waits for the database before reporting it as down.
    health_db_timeout_seconds: float = 2.0
    local_user_email: str = "local@studysensei.dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()
