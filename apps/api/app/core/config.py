from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]


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
    max_upload_bytes: int = 50 * 1024 * 1024
    # How long the job worker sleeps when the queue is empty.
    worker_poll_seconds: float = 1.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
