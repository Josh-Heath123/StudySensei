"""Migration 0004 maps old module colours to the nearest design-system swatch."""

import importlib.util
import uuid
from pathlib import Path
from types import ModuleType

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Module, User

PATH = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0004_module_swatches.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0004", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = load()


@pytest.mark.parametrize("swatch", migration.SWATCHES)
def test_every_swatch_maps_to_itself(swatch: str) -> None:
    assert migration.nearest_swatch(swatch) == swatch


@pytest.mark.parametrize(
    ("old", "expected"),
    [
        ("#007AFF", "#8FB8FF"),  # iOS blue -> Blue
        ("#5856D6", "#C9A7FF"),  # indigo -> Lilac
        ("#AF52DE", "#C9A7FF"),  # purple -> Lilac
        ("#FF2D55", "#FF8FA3"),  # pink-red -> Pink
        ("#FF9500", "#FF7A3D"),  # orange -> Orange
        ("#FFCC00", "#FFD23F"),  # yellow -> Yellow
        ("#34C759", "#5EE0B0"),  # green -> Mint
        ("#00C7BE", "#5EE0B0"),  # teal -> Mint
        ("#808080", "#6ED3E8"),  # grey: no hue, so nearest by Lab distance (Cyan)
    ],
)
def test_old_presets_map_to_a_sensible_swatch(old: str, expected: str) -> None:
    assert migration.nearest_swatch(old) == expected


async def test_upgrade_rewrites_existing_modules(session: AsyncSession, user_a: User) -> None:
    rows = {
        "#007AFF": Module(
            id=uuid.uuid4(), user_id=user_a.id, code="A1", name="A", colour="#007AFF"
        ),
        "#5EE0B0": Module(
            id=uuid.uuid4(), user_id=user_a.id, code="A2", name="B", colour="#5EE0B0"
        ),
        "#ff9500": Module(
            id=uuid.uuid4(), user_id=user_a.id, code="A3", name="C", colour="#ff9500"
        ),
    }
    session.add_all(rows.values())
    await session.flush()

    def run(sync_connection: object) -> None:
        context = MigrationContext.configure(sync_connection)  # type: ignore[arg-type]
        with Operations.context(context):
            migration.upgrade()

    connection = await session.connection()
    await connection.run_sync(run)

    result = await session.execute(
        select(Module.id, Module.colour).where(Module.user_id == user_a.id)
    )
    colours = {row.id: row.colour for row in result}
    assert colours == {
        rows["#007AFF"].id: "#8FB8FF",
        rows["#5EE0B0"].id: "#5EE0B0",
        rows["#ff9500"].id: "#FF7A3D",
    }
