"""
app/schemas.py — Pydantic schemas for API request/response contracts.

These are the data shapes that FastAPI uses to validate incoming request bodies
and serialize outgoing responses. They are intentionally decoupled from the
SQLAlchemy ORM models so the API surface can evolve independently.
"""

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.source import SourceType
from app.models.article import ProcessingStatus


# ── Source Schemas ─────────────────────────────────────────────────────────────

class SourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: SourceType
    url: str
    is_active: bool
    fetched_till: Optional[datetime]
    last_fetched_at: Optional[datetime]
    failure_count: int
    created_at: datetime
    updated_at: datetime


class SourceCreate(BaseModel):
    name: str
    type: SourceType
    url: str


class SourceUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    is_active: Optional[bool] = None


# ── Article Schemas ────────────────────────────────────────────────────────────

class ArticleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    url: str
    source_id: uuid.UUID
    processing_status: ProcessingStatus
    summary: Optional[str]
    published_at: datetime
    scraped_at: datetime
    created_at: datetime


class ArticleDetailResponse(ArticleResponse):
    """Full article response including raw/cleaned content and token count."""
    raw_content: str
    cleaned_content: Optional[str]
    token_count: Optional[int]


# ── Digest Schemas ─────────────────────────────────────────────────────────────

class DigestListResponse(BaseModel):
    """Lightweight digest list item — no content blobs."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    digest_date: date
    article_count: int
    model_used: str
    sent_at: Optional[datetime]
    created_at: datetime


class DigestResponse(DigestListResponse):
    """Full digest response including HTML and Markdown content."""
    markdown_content: str
    html_content: str
    prompt_version: str


# ── Health / Status Schemas ────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime


class PipelineStatusResponse(BaseModel):
    last_run_date: Optional[date]
    total_sources: int
    active_sources: int
    total_articles: int
    total_digests: int


class PipelineRunResponse(BaseModel):
    message: str
    started_at: datetime
