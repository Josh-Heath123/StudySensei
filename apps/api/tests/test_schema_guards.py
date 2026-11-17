"""Guards that keep the schema honest as tables are added."""

from pathlib import Path

from alembic import command
from alembic.config import Config

from app.models import Base

# Tables allowed without a user_id column. Child tables are only allowed when a
# composite FK ties them to a user-owned parent (see app/models/academics.py).
NO_USER_ID = {
    "users",
    "assessment_topics",  # (assessment_id, module_id) and (topic_id, module_id) FKs
    "session_topic_ratings",  # (session_id, module_id) and (topic_id, module_id) FKs
    "chunk_topics",  # (chunk_id, module_id) and (topic_id, module_id) FKs
}


def test_every_table_is_owned_by_a_user() -> None:
    missing = {
        table.name
        for table in Base.metadata.sorted_tables
        if "user_id" not in table.c and table.name not in NO_USER_ID
    }
    assert missing == set(), f"Add user_id (or justify in NO_USER_ID): {sorted(missing)}"


def test_models_match_migrations(migrated_db: None) -> None:
    """Fails if a model changed without a migration (alembic check)."""
    command.check(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")))
