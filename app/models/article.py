"""
app/models/article.py — Article model.

An Article is a single piece of content fetched from a Source.
processing_status tracks its journey through the pipeline stages.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin

import enum


class ProcessingStatus(str, enum.Enum):
    fetched = "fetched"
    cleaned = "cleaned"
    summarized = "summarized"
    included_in_digest = "included_in_digest"
    failed = "failed"


class Article(TimestampMixin, Base):
    __tablename__ = "articles"
    __table_args__ = (
        UniqueConstraint("url", name="uq_articles_url"),
        UniqueConstraint("content_hash", name="uq_articles_content_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    cleaned_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    processing_status: Mapped[ProcessingStatus] = mapped_column(
        Enum(ProcessingStatus, name="processing_status"),
        default=ProcessingStatus.fetched,
        nullable=False,
    )
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Relationship — lazy loaded, used for debugging/admin only
    source: Mapped["Source"] = relationship("Source", lazy="select")  # type: ignore[name-defined]

    def __repr__(self) -> str:
        return f"<Article title={self.title!r} status={self.processing_status}>"
