"""
app/api/routes/health.py — Health and pipeline status endpoints.

GET /api/v1/health            → Basic service liveness check
GET /api/v1/health/status     → Per-user ingestion status (sources, counts, timestamps)
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.app import APP_VERSION
from app.database import get_db_session
from app.models import Source, User, UserSourceAlias
from app.schemas import HealthResponse, PipelineStatusResponse, SourceResponse
from app.api.routes.users import get_or_create_user
from app.api.routes.sources import _to_response

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
def health_check():
    """Basic service liveness check."""
    return HealthResponse(
        status="ok",
        version=APP_VERSION,
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/health/status", response_model=PipelineStatusResponse)
def pipeline_status(
    email: str = Query(..., description="User email to fetch status for"),
    db: Session = Depends(get_db_session),
):
    """
    Per-user pipeline status.

    Returns the user's digest schedule, last delivery timestamp, and the
    ingestion status (last_fetched_at, fetched_till, failure_count) of every
    source they are subscribed to.
    """
    user = get_or_create_user(email, db)

    # Fetch sources and user's display names in a single JOIN — no N+1
    rows = (
        db.query(Source, UserSourceAlias.display_name)
        .join(
            UserSourceAlias,
            (UserSourceAlias.source_id == Source.id)
            & (UserSourceAlias.user_id == user.id),
        )
        .all()
    )

    return PipelineStatusResponse(
        user_email=user.email,
        digest_time=user.digest_time,
        last_digest_at=user.last_digest_at,
        sources=[_to_response(source, display_name) for source, display_name in rows],
    )
