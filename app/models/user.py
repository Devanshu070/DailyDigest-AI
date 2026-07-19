"""
app/models/user.py — User model.

A User is a subscriber of DailyDigest.
- interests_md:             their personal interest profile (used to personalize the digest)
- digest_time:              daily delivery time in UTC (e.g. time(6, 0) = 06:00 UTC)
- last_digest_at:           timestamp of the most recent email sent (scheduled OR manual).
                            Used by the frontend/API to display "last delivery" information.
- last_scheduled_digest_at: timestamp of the last SCHEDULED run that successfully sent email.
                            Used exclusively by the scheduler's skip guard to prevent
                            double-delivery on the same day. Manual runs do NOT update this.
"""

import uuid
from datetime import datetime, time

from sqlalchemy import Boolean, DateTime, String, Text, Time
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)

    # Inline markdown — this user's personal interest profile.
    # Used by the digest assembler to decide what to include / skip.
    interests_md: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Daily digest time in UTC (e.g., time(6, 0) = 06:00 UTC = 11:30 IST).
    # The cron runs every few hours; the runner checks if this time has passed
    # and the user hasn't received a digest in the last 24h.
    digest_time: Mapped[time] = mapped_column(
        Time(timezone=False), nullable=False, default=time(6, 0)
    )

    # UI-facing timestamp: when we last successfully sent a digest to this user
    # (whether triggered by the scheduler or a manual API call).
    # The frontend reads this to display "last delivery" information.
    # None = no digest has ever been sent.
    last_digest_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Scheduler bookkeeping: when the scheduled pipeline last successfully sent email.
    # The scheduler's skip guard reads ONLY this column to decide whether a user
    # has already received their digest today. Manual runs do NOT update this field,
    # so manual runs cannot accidentally suppress the next scheduled delivery.
    # None = no scheduled digest has ever been sent.
    last_scheduled_digest_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # When true, scheduled digest delivery is skipped. Manual runs remain available.
    digest_paused: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<User email={self.email!r} "
            f"digest_time={self.digest_time}>"
        )
