"""
app/schemas.py — Pydantic schemas for API request/response contracts.

These are the data shapes that FastAPI uses to validate incoming request bodies
and serialize outgoing responses. They are intentionally decoupled from the
SQLAlchemy ORM models so the API surface can evolve independently.
"""

import uuid
from datetime import datetime, time
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.source import SourceType


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
    last_error: Optional[str]
    created_at: datetime
    updated_at: datetime


class SourceCreate(BaseModel):
    name: str
    type: SourceType
    url: str


class SourceCreateMany(BaseModel):
    sources: list[SourceCreate]


# ── Article Schemas ────────────────────────────────────────────────────────────

class ArticleListItem(BaseModel):
    """Lightweight article card for feed lists — title + metadata only."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    source_id: uuid.UUID
    published_at: datetime


class ArticleResponse(BaseModel):
    """Full article card shown when user taps into an article — summary + link."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    url: str
    source_id: uuid.UUID
    summary: Optional[str]
    published_at: datetime


# ── User Schemas ───────────────────────────────────────────────────────────────

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    email: str
    digest_time: time
    interests_md: str


class UserDigestTimeUpdate(BaseModel):
    digest_time: time


class UserInterestsUpdate(BaseModel):
    interests_md: str


# ── Health / Status Schemas ────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime


class PipelineStatusResponse(BaseModel):
    user_email: str
    digest_time: time
    last_digest_at: Optional[datetime]
    sources: list[SourceResponse]


class PipelineRunResponse(BaseModel):
    message: str
    started_at: datetime
