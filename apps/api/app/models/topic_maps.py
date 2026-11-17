"""AI topic maps (decision 0006): per-material proposals, cited pages, and chunk links.

- ``topic_proposals``: one per material, what the AI found in it (validated JSON) and
  which model answered. Re-running the material's extraction replaces it.
- ``topic_pages``: the pages each topic was drawn from (from the proposals the merge
  cited). Kept apart from chunks, so re-indexing a material doesn't lose them.
- ``chunk_topics``: derived links from chunks to topics, rebuilt from the two sources
  above (``pages``) and from local embeddings (``similarity``). No AI is involved.

Isolation follows ``app/models/academics.py``: composite foreign keys tie each row to
parents in the same module (and user), and cascades remove rows with their parents.
"""

import uuid
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.academics import _in
from app.models.base import TimestampedBase

LINK_METHODS = ("pages", "similarity")


class TopicProposal(TimestampedBase):
    __tablename__ = "topic_proposals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["material_id", "user_id"], ["materials.id", "materials.user_id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["material_id", "module_id"],
            ["materials.id", "materials.module_id"],
            ondelete="CASCADE",
        ),
        # One proposal per material: a re-run replaces it.
        UniqueConstraint("material_id", name="uq_topic_proposals_material"),
        Index("ix_topic_proposals_user_module", "user_id", "module_id"),
    )

    user_id: Mapped[uuid.UUID]
    module_id: Mapped[uuid.UUID]
    material_id: Mapped[uuid.UUID]
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(100))
    # ``schemas.topic_maps.MaterialTopics`` as JSON, page numbers checked against the material.
    topics: Mapped[dict[str, Any]] = mapped_column(JSONB)


class TopicPage(TimestampedBase):
    """A page a topic was drawn from, as cited by the merge (one row per page)."""

    __tablename__ = "topic_pages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["topic_id", "user_id"], ["topics.id", "topics.user_id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["topic_id", "module_id"], ["topics.id", "topics.module_id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["material_id", "module_id"],
            ["materials.id", "materials.module_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("topic_id", "material_id", "page_number", name="uq_topic_pages"),
        CheckConstraint("page_number >= 1", name="ck_topic_pages_number"),
        Index("ix_topic_pages_user_module", "user_id", "module_id"),
    )

    user_id: Mapped[uuid.UUID]
    module_id: Mapped[uuid.UUID]
    topic_id: Mapped[uuid.UUID]
    material_id: Mapped[uuid.UUID]
    page_number: Mapped[int] = mapped_column(Integer)


class ChunkTopic(TimestampedBase):
    """A chunk linked to a topic, by a cited page or by meaning (decision 0006).

    Like ``assessment_topics`` it has no ``user_id``: composite FKs through ``module_id``
    tie it to a chunk and a topic in the same module, and deleting either removes it.
    """

    __tablename__ = "chunk_topics"
    __table_args__ = (
        ForeignKeyConstraint(
            ["chunk_id", "module_id"], ["chunks.id", "chunks.module_id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["topic_id", "module_id"], ["topics.id", "topics.module_id"], ondelete="CASCADE"
        ),
        UniqueConstraint("chunk_id", "topic_id", name="uq_chunk_topics"),
        CheckConstraint(_in("method", LINK_METHODS), name="ck_chunk_topics_method"),
        CheckConstraint("score >= -1 AND score <= 1", name="ck_chunk_topics_score"),
        Index("ix_chunk_topics_topic", "topic_id"),
        Index("ix_chunk_topics_module", "module_id"),
    )

    module_id: Mapped[uuid.UUID]
    chunk_id: Mapped[uuid.UUID]
    topic_id: Mapped[uuid.UUID]
    # Cosine similarity of the chunk and the topic's "name: description" (1.0 for pages).
    score: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(20))
