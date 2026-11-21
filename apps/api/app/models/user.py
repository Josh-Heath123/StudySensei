from sqlalchemy import CheckConstraint, Double, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedBase


class User(TimestampedBase):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "daily_study_cap_minutes BETWEEN 15 AND 1440", name="ck_users_daily_study_cap"
        ),
        CheckConstraint("reminder_minutes IN (5, 10, 15, 30)", name="ck_users_reminder_minutes"),
        CheckConstraint(
            "practice_new_per_day BETWEEN 0 AND 200", name="ck_users_practice_new_per_day"
        ),
        CheckConstraint(
            "practice_desired_retention BETWEEN 0.80 AND 0.97",
            name="ck_users_practice_desired_retention",
        ),
    )

    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    # Planning (migration 0021). An IANA name, checked against zoneinfo by the schema.
    timezone: Mapped[str] = mapped_column(
        String(64), default="Africa/Johannesburg", server_default="Africa/Johannesburg"
    )
    daily_study_cap_minutes: Mapped[int] = mapped_column(Integer, default=180, server_default="180")
    # Minutes before a block that its push reminder is sent; null means off (decision 0024).
    reminder_minutes: Mapped[int | None] = mapped_column(
        Integer, default=10, server_default="10", nullable=True
    )
    # Practice (migration 0026, decision 0026): new items a day, and FSRS's desired retention.
    practice_new_per_day: Mapped[int] = mapped_column(Integer, default=20, server_default="20")
    practice_desired_retention: Mapped[float] = mapped_column(
        Double, default=0.9, server_default="0.9"
    )
