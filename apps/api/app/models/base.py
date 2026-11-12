import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampedBase(Base):
    """UUID primary key plus created_at / updated_at, shared by every table."""

    __abstract__ = True
    # Fetch server-set columns (created_at, updated_at) with RETURNING on insert
    # and update; otherwise reading them later triggers a lazy load, which fails
    # under asyncio.
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012 (SQLAlchemy declares it non-ClassVar)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
