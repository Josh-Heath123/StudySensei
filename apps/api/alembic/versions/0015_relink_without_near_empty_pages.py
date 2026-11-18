"""Relink every module with a topic map now that near-empty pages aren't similarity candidates.

Data only. Similarity linking now skips pages with less than TOPIC_LINK_MIN_PAGE_CHARS
of text (title slides, "Chapter N" dividers, caption-only slides). Existing links were
built before that, so each module that has a topic map gets one link_topics job. Linking
makes no AI call, keeps cited pages, and never relinks a page the student unlinked.

A module "has a topic map" when it has chunk links, or a merge that succeeded.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def queue_relinking() -> None:
    """One link_topics job per module with a topic map, unless one is already queued."""
    op.execute(
        """
        INSERT INTO jobs (id, user_id, kind, payload)
        SELECT gen_random_uuid(), m.user_id, 'link_topics',
               jsonb_build_object('module_id', m.id::text)
        FROM modules m
        WHERE (
            EXISTS (SELECT 1 FROM chunk_topics ct WHERE ct.module_id = m.id)
            OR EXISTS (
                SELECT 1 FROM jobs j
                WHERE j.user_id = m.user_id
                  AND j.kind = 'merge_topics'
                  AND j.status = 'succeeded'
                  AND j.payload ->> 'module_id' = m.id::text
            )
          )
          AND NOT EXISTS (
            SELECT 1 FROM jobs j
            WHERE j.user_id = m.user_id
              AND j.kind = 'link_topics'
              AND j.status = 'queued'
              AND j.payload ->> 'module_id' = m.id::text
          )
        """
    )


def upgrade() -> None:
    queue_relinking()


def downgrade() -> None:
    # Nothing to undo: the links a relink built are as valid as the ones before.
    pass
