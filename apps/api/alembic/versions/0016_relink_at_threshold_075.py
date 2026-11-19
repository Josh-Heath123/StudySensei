"""Relink every module with a topic map now that the similarity threshold is 0.75.

Data only. TOPIC_LINK_THRESHOLD's default went from 0.63 to 0.75 (evals/linking on COS330,
18 Nov 2026: it kept 88 % of the same-chapter links and halved the cross-chapter ones).
Existing similarity links were built at 0.63, so each module that has a topic map gets one
link_topics job, as in 0015. Linking makes no AI call, keeps cited pages, and never relinks
a page the student unlinked.

A module "has a topic map" when it has chunk links, or a merge that succeeded.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
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
