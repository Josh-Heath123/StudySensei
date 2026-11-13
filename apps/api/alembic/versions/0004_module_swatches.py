"""Map every module colour to the nearest design-system swatch (data only).

Design system v1 (docs/DESIGN.md) uses module colours as fills behind ink
(#111111) text, from a fixed set of 8 swatches that all reach 4.5:1 against it.
Existing modules used darker iOS-style presets, so each colour is replaced by the
swatch closest in hue (CIE LCh). The swatches are all light, so hue is what reads
as "the same colour"; plain Lab distance would turn iOS blue into lilac. Near-greys
have no meaningful hue and go to the closest swatch by Lab distance instead.

The old colours aren't kept, so the downgrade can't restore them.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-13
"""

import math
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen copy of apps/web/src/features/modules/colours.ts at the time of this migration.
SWATCHES = (
    "#FF7A3D",  # Orange
    "#FFD23F",  # Yellow
    "#5EE0B0",  # Mint
    "#8FB8FF",  # Blue
    "#C9A7FF",  # Lilac
    "#FF8FA3",  # Pink
    "#B8E05E",  # Lime
    "#6ED3E8",  # Cyan
)


def _linear(channel: int) -> float:
    c = channel / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def to_lab(hex_colour: str) -> tuple[float, float, float]:
    """sRGB "#RRGGBB" -> CIELAB (D65)."""
    r, g, b = (_linear(int(hex_colour[i : i + 2], 16)) for i in (1, 3, 5))
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


# Below this chroma a colour is close to grey, and its hue angle is noise.
GREY_CHROMA = 15.0


def _hue_gap(a: float, b: float) -> float:
    gap = abs(a - b) % 360
    return min(gap, 360 - gap)


def nearest_swatch(hex_colour: str) -> str:
    lightness, a, b = to_lab(hex_colour)

    def lab_distance(swatch: str) -> float:
        return math.dist((lightness, a, b), to_lab(swatch))

    if math.hypot(a, b) < GREY_CHROMA:
        return min(SWATCHES, key=lab_distance)
    hue = math.degrees(math.atan2(b, a))

    def hue_distance(swatch: str) -> tuple[float, float]:
        _, sa, sb = to_lab(swatch)
        return _hue_gap(hue, math.degrees(math.atan2(sb, sa))), lab_distance(swatch)

    return min(SWATCHES, key=hue_distance)


def upgrade() -> None:
    connection = op.get_bind()
    modules = sa.table("modules", sa.column("id", sa.Uuid()), sa.column("colour", sa.String()))
    for module_id, colour in connection.execute(sa.select(modules.c.id, modules.c.colour)):
        new = nearest_swatch(colour.upper())
        if new != colour:
            connection.execute(modules.update().where(modules.c.id == module_id).values(colour=new))


def downgrade() -> None:
    # Data only: the original colours were overwritten and can't be recovered.
    pass
