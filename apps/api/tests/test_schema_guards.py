"""Guards that keep the schema honest as tables are added."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import UniqueConstraint

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


# User-owned tables whose rows reference other users' rows only through composite FKs that
# include user_id (decision 0021). Each needs UNIQUE (id, user_id) for its own children.
COMPOSITE_PARENTS = {
    "plan_versions": set(),
    "plan_blocks": {"plan_versions", "modules", "assessments", "topics"},
    # Practice (ADR 0025); their topic FKs go through module_id.
    "practice_generations": {"modules"},
    "practice_items": {"modules", "practice_generations"},
}


def test_plan_and_practice_tables_are_isolated_by_composite_keys() -> None:
    tables = {table.name: table for table in Base.metadata.sorted_tables}
    for name, parents in COMPOSITE_PARENTS.items():
        table = tables[name]
        uniques = {
            tuple(c.name for c in constraint.columns)
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        assert ("id", "user_id") in uniques, name
        composite = {
            fk.referred_table.name
            for fk in table.foreign_key_constraints
            if "user_id" in fk.column_keys and len(fk.column_keys) == 2
        }
        assert composite == parents, name
    # A session's planned block is the same user's.
    sessions = tables["study_sessions"]
    assert any(
        fk.referred_table.name == "plan_blocks" and fk.column_keys == ["plan_block_id", "user_id"]
        for fk in sessions.foreign_key_constraints
    )
