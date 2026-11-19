"""Voice timing on answers: release of push-to-talk to the first spoken word.

- messages.voice_latency_ms: for a question asked by voice, measured in the browser from
  releasing push-to-talk to the first spoken word of the answer (ADR 0015).
- messages.voice_timing (JSONB): its parts in ms from release: transcript_ms,
  first_token_ms, first_sentence_ms.
- Only an answer can carry them (ck_messages_voice_latency). No audio is ever stored.

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("voice_latency_ms", sa.Integer(), nullable=True))
    op.add_column("messages", sa.Column("voice_timing", postgresql.JSONB(), nullable=True))
    op.create_check_constraint(
        "ck_messages_voice_latency",
        "messages",
        "voice_latency_ms IS NULL OR (role = 'assistant' AND voice_latency_ms >= 0)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_messages_voice_latency", "messages", type_="check")
    op.drop_column("messages", "voice_timing")
    op.drop_column("messages", "voice_latency_ms")
