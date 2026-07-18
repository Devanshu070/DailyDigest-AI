"""
app/api/routes/sources.py — User-scoped source management.

All endpoints require ?email= to identify the user.

GET    /api/v1/sources              → List sources the user is subscribed to (with their display names)
POST   /api/v1/sources              → Add one or more sources and subscribe the user to each
DELETE /api/v1/sources/{id}         → Unsubscribe the user from a source (global record is kept)

Design notes:
  - Sources are globally unique, de-duplicated by normalized URL.
  - Per-user display names are stored in UserSourceAlias.
  - All list queries use a single JOIN to avoid N+1 queries.
"""

import uuid
from urllib.parse import urlparse, urlunparse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db_session
from app.models import Source, UserSourceAlias
from app.schemas import SourceCreateMany, SourceResponse
from app.api.routes.users import get_or_create_user

router = APIRouter(prefix="/sources", tags=["Sources"])


# ── URL normalisation ──────────────────────────────────────────────────────────

def _normalize_url(raw: str) -> str:
    """
    Canonicalize a URL so equivalent inputs map to a single source record.

    Rules:
      - Lowercase scheme and host
      - Strip leading 'www.'
      - Strip trailing slash from path
      - Preserve query string and fragment as-is

    YouTube channel-ID resolution is left as a future enhancement.
    """
    parsed = urlparse(raw.strip())
    scheme = (parsed.scheme or "https").lower()
    netloc = (parsed.netloc or parsed.path).lower()
    # Use startswith to strip exactly "www." — lstrip would incorrectly strip
    # any leading combination of 'w' and '.' characters.
    if netloc.startswith("www."):
        netloc = netloc[4:]
    host   = netloc
    path   = parsed.path.rstrip("/") if parsed.netloc else ""
    return urlunparse((scheme, host, path, parsed.params, parsed.query, parsed.fragment))


# ── Helper: build SourceResponse from ORM row + alias name ────────────────────

def _to_response(source: Source, display_name: str) -> SourceResponse:
    return SourceResponse(
        id=source.id,
        display_name=display_name,
        type=source.type,
        url=source.url,
        is_active=source.is_active,
        fetched_till=source.fetched_till,
        last_fetched_at=source.last_fetched_at,
        failure_count=source.failure_count,
        last_error=source.last_error,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[SourceResponse])
def list_user_sources(
    email: str = Query(..., description="User email"),
    db: Session = Depends(get_db_session),
):
    """
    List sources that this user is subscribed to, including their personal display name.

    Uses a single JOIN query to avoid N+1 lookups against user_source_aliases.
    """
    user = get_or_create_user(email, db)

    rows = (
        db.query(Source, UserSourceAlias.display_name)
        .join(
            UserSourceAlias,
            (UserSourceAlias.source_id == Source.id)
            & (UserSourceAlias.user_id == user.id),
        )
        .order_by(UserSourceAlias.display_name)
        .all()
    )

    return [_to_response(source, display_name) for source, display_name in rows]


@router.post("", response_model=list[SourceResponse], status_code=status.HTTP_201_CREATED)
def create_and_subscribe(
    body: SourceCreateMany,
    email: str = Query(..., description="User email"),
    db: Session = Depends(get_db_session),
):
    """
    Add one or more sources and subscribe this user to each.

    - The URL is normalized before lookup; duplicate URLs reuse the existing Source.
    - The user's display name (body.sources[].name) is stored in user_source_aliases.
    - Re-adding an already-subscribed source updates the display name (upsert).

    Example body:
    {
        "sources": [
            {"name": "AI News",  "type": "youtube", "url": "https://youtube.com/@OpenAI"},
            {"name": "Anthropic Blog", "type": "blog", "url": "https://anthropic.com/news"}
        ]
    }
    """
    user = get_or_create_user(email, db)
    result: list[SourceResponse] = []

    for item in body.sources:
        canonical_url = _normalize_url(item.url)

        # Find or create the global Source record (no name — URL is the identity)
        source = db.query(Source).filter_by(url=canonical_url).first()
        if not source:
            source = Source(type=item.type, url=canonical_url)
            db.add(source)
            db.flush()  # populate source.id

        # Upsert the user's display name alias
        alias = (
            db.query(UserSourceAlias)
            .filter_by(user_id=user.id, source_id=source.id)
            .first()
        )
        if alias:
            alias.display_name = item.name  # update if re-added with a new name
        else:
            db.add(UserSourceAlias(
                user_id=user.id,
                source_id=source.id,
                display_name=item.name,
            ))

        result.append(_to_response(source, item.name))

    return result


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def unsubscribe_source(
    source_id: uuid.UUID,
    email: str = Query(..., description="User email"),
    db: Session = Depends(get_db_session),
):
    """
    Unsubscribe the user from a source.

    Removes the user's alias row. The global Source record in the sources table is NOT deleted.
    """
    user = get_or_create_user(email, db)

    # Remove alias
    alias = db.query(UserSourceAlias).filter_by(user_id=user.id, source_id=source_id).first()
    if not alias:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You are not subscribed to this source",
        )

    db.delete(alias)
