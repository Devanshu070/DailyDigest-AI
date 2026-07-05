"""
app/models/digest.py — DailyDigest model.

One digest is created per run. Stores the full markdown and HTML output
from the Step 2 LLM assembly, plus delivery metadata.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin


class DailyDigest(TimestampMixin, Base):
    __tablename__ = "daily_digests"
    __table_args__ = (
        UniqueConstraint("digest_date", name="uq_daily_digests_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    digest_date: Mapped[date] = mapped_column(Date, nullable=False)

    markdown_content: Mapped[str] = mapped_column(Text, nullable=False)
    html_content: Mapped[str] = mapped_column(Text, nullable=False)

    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    model_used: Mapped[str] = mapped_column(String(128), nullable=False)
    article_count: Mapped[int] = mapped_column(Integer, nullable=False)

    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<DailyDigest date={self.digest_date} articles={self.article_count} sent={self.sent_at is not None}>"
