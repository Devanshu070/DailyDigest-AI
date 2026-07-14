"""
app/api/routes/sources.py — User-scoped source management.

All endpoints require ?email= to identify the user.

GET    /api/v1/sources              → List sources the user is subscribed to
POST   /api/v1/sources              → Create one or more sources and subscribe the user to them
DELETE /api/v1/sources/{id}         → Unsubscribe the user from a source (global record is kept)
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db_session
from app.models import Source, User
from app.schemas import SourceCreateMany, SourceResponse

router = APIRouter(prefix="/sources", tags=["Sources"])


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_user(email: str, db: Session) -> User:
    """Fetch an active user by email or raise 404."""
    user = db.query(User).filter_by(email=email, is_active=True).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User '{email}' not found")
    return user


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[SourceResponse])
def list_user_sources(
    email: str = Query(..., description="User email"),
    db: Session = Depends(get_db_session),
):
    """List sources that this user is subscribed to."""
    user = _get_user(email, db)
    source_ids = user.source_ids or []
    if not source_ids:
        return []
    return db.query(Source).filter(Source.id.in_(source_ids)).order_by(Source.name).all()



@router.post("", response_model=list[SourceResponse], status_code=status.HTTP_201_CREATED)
def create_and_subscribe(
    body: SourceCreateMany,
    email: str = Query(..., description="User email"),
    db: Session = Depends(get_db_session),
):
    """
    Create one or more sources and subscribe this user to each of them.

    If a source with the same URL already exists, it is reused — not duplicated.
    Already-subscribed sources are silently skipped.

    Example body:
    {
        "sources": [
            {"name": "Fireship", "type": "youtube", "url": "https://..."},
            {"name": "Anthropic Blog", "type": "blog", "url": "https://..."}
        ]
    }
    """
    user = _get_user(email, db)
    subscribed_ids = set(user.source_ids or [])
    result = []

    for item in body.sources:
        # Reuse existing source if the URL is already in the DB
        source = db.query(Source).filter_by(url=item.url).first()
        if not source:
            source = Source(name=item.name, type=item.type, url=item.url)
            db.add(source)
            db.flush()

        if source.id not in subscribed_ids:
            subscribed_ids.add(source.id)

        result.append(source)

    user.source_ids = list(subscribed_ids)
    db.flush()
    return result


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def unsubscribe_source(
    source_id: uuid.UUID,
    email: str = Query(..., description="User email"),
    db: Session = Depends(get_db_session),
):
    """
    Unsubscribe the user from a source by removing it from their source_ids.
    The global source record in the sources table is NOT deleted.
    """
    user = _get_user(email, db)

    if source_id not in (user.source_ids or []):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You are not subscribed to this source",
        )

    user.source_ids = [sid for sid in user.source_ids if sid != source_id]
    db.flush()
