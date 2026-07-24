"""
app/api/routes/sources.py — User-scoped source management.

All endpoints require ?email= to identify the user.

GET    /api/v1/sources              → List sources the user is subscribed to (with their display names)
POST   /api/v1/sources              → Add one or more sources and subscribe the user to each
DELETE /api/v1/sources/{id}         → Unsubscribe the user from a source (global record is kept)
GET    /api/v1/sources/suggestions  → AI-powered source suggestions based on user interests

Design notes:
  - Sources are globally unique, de-duplicated by normalized URL.
  - Per-user display names are stored in UserSourceAlias.
  - All list queries use a single JOIN to avoid N+1 queries.
"""

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db_session
from app.ingestion.blog.ingester import BlogIngester
from app.ingestion.youtube.ingester import YouTubeIngester
from app.models import Source, SourceType, UserSourceAlias
from app.schemas import (
    SourceCheckRequest,
    SourceCheckResponse,
    SourceCreateMany,
    SourceResponse,
    SourceSuggestionsResponse,
)
from app.api.routes.users import get_or_create_user
from app.utils.url_validation import normalize_url

router = APIRouter(prefix="/sources", tags=["Sources"])
log = logging.getLogger(__name__)


# ── URL normalisation ──────────────────────────────────────────────────────────
# normalize_url is imported from app.utils.url_validation — single source of
# truth shared with the source suggestions pipeline.


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


def _validate_check_url(source_type: SourceType, raw_url: str) -> str:
    """Validate the minimum URL shape required by the source ingesters."""
    candidate = raw_url.strip()
    if "://" not in candidate:
        candidate = f"https://{candidate}"

    parsed = urlparse(candidate)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or any(character.isspace() for character in parsed.netloc)
    ):
        raise ValueError("Enter a complete URL, such as https://example.com/feed")

    if source_type == SourceType.youtube and parsed.hostname.lower() not in {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
    }:
        raise ValueError("YouTube sources must use a youtube.com channel URL")

    return candidate


def _test_source(
    source_type: SourceType,
    raw_url: str,
    source_id: uuid.UUID | None = None,
) -> SourceCheckResponse:
    """Fetch a source without parsing, persisting, or sending anything."""
    try:
        url = _validate_check_url(source_type, raw_url)
    except ValueError as exc:
        return SourceCheckResponse(
            source_id=source_id,
            ok=False,
            status="invalid_url",
            message=str(exc),
        )

    try:
        ingester = YouTubeIngester() if source_type == SourceType.youtube else BlogIngester()
        entries = ingester.fetch(url)
        item_count = len(entries or [])
        return SourceCheckResponse(
            source_id=source_id,
            ok=True,
            status="healthy",
            message=f"Source is readable. Found {item_count} item(s).",
            item_count=item_count,
        )
    except Exception:
        log.exception("Source test failed for %s", raw_url)
        return SourceCheckResponse(
            source_id=source_id,
            ok=False,
            status="temporary_error",
            message=(
                "We could not read this source right now. It may be temporarily "
                "unavailable, or the URL may no longer be valid."
            ),
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
        canonical_url = normalize_url(item.url)

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


@router.post("/check", response_model=SourceCheckResponse)
def test_new_source(body: SourceCheckRequest):
    """Test a source before adding it; this endpoint does not change the database."""
    return _test_source(body.type, body.url)


@router.post("/check-all", response_model=list[SourceCheckResponse])
def test_all_sources(
    email: str = Query(..., description="User email"),
    db: Session = Depends(get_db_session),
):
    """Test every source subscribed to by the current user."""
    user = get_or_create_user(email, db)
    rows = (
        db.query(Source.id, Source.type, Source.url)
        .join(
            UserSourceAlias,
            (UserSourceAlias.source_id == Source.id)
            & (UserSourceAlias.user_id == user.id),
        )
        .all()
    )

    # Network failures can take several seconds because the ingesters retry.
    # Run independent source tests concurrently while keeping DB work outside
    # the worker threads.
    max_workers = min(4, len(rows)) or 1
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        return list(
            executor.map(
                lambda row: _test_source(row.type, row.url, row.id),
                rows,
            )
        )


@router.post("/{source_id}/check", response_model=SourceCheckResponse)
def test_existing_source(
    source_id: uuid.UUID,
    email: str = Query(..., description="User email"),
    db: Session = Depends(get_db_session),
):
    """Test one source after confirming that the user is subscribed to it."""
    user = get_or_create_user(email, db)
    source = (
        db.query(Source)
        .join(
            UserSourceAlias,
            (UserSourceAlias.source_id == Source.id)
            & (UserSourceAlias.user_id == user.id),
        )
        .filter(Source.id == source_id)
        .first()
    )
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You are not subscribed to this source",
        )

    return _test_source(source.type, source.url, source.id)


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


# ── Source Suggestions ─────────────────────────────────────────────────────────

def _build_suggestion_service():
    """
    Factory that constructs the module-level SuggestionService singleton.

    Called once at import time. All pipeline dependencies are wired here so
    the API route stays thin (no business logic).
    """
    import logging as _logging

    from app.config import settings
    from app.llm import llm_assembler
    from app.recommendations.service import RecommendationService
    from app.suggestions.service import SuggestionService
    from app.utils.suggestion_validation import SuggestionValidator

    _log = _logging.getLogger(__name__)

    if settings.exa_api_key:
        from app.search.exa import ExaSearchProvider
        search_provider = ExaSearchProvider(api_key=settings.exa_api_key)
        _log.info("SuggestionService: using ExaSearchProvider")
    else:
        # No API key — use a no-op provider so the endpoint still returns []
        # gracefully without raising at startup.
        from app.search.base import SearchProvider, SearchResult as _SR

        class _NoOpSearchProvider(SearchProvider):
            def search(self, query: str, num_results: int = 5) -> list[_SR]:
                _log.warning(
                    "SuggestionService: EXA_API_KEY is not configured — "
                    "returning empty suggestions."
                )
                return []

        search_provider = _NoOpSearchProvider()

    return SuggestionService(
        search_provider=search_provider,
        recommendation_service=RecommendationService(llm=llm_assembler),
        validator=SuggestionValidator(),
    )


# Module-level singleton — instantiated once, reused across all requests.
_suggestion_service: "SuggestionService | None" = None  # type: ignore[name-defined]


def get_suggestion_service():
    """FastAPI dependency that returns the shared SuggestionService instance."""
    global _suggestion_service
    if _suggestion_service is None:
        from app.suggestions.service import SuggestionService as _SS
        _suggestion_service = _build_suggestion_service()
    return _suggestion_service


@router.get("/suggestions", response_model=SourceSuggestionsResponse)
def get_source_suggestions(
    email: str = Query(..., description="User email"),
    refresh: bool = Query(False, description="Bypass cache and regenerate suggestions"),
    db: Session = Depends(get_db_session),
    suggestion_service=Depends(get_suggestion_service),
):
    """
    Return personalised source suggestions based on the user's interests.

    Flow:
      1. Load user and their existing subscriptions.
      2. Pass interests + subscriptions to SuggestionService.
      3. SuggestionService runs: query gen → Exa search → LLM ranking → validation.
      4. Results are cached for 24 h per user; pass ?refresh=true to force regeneration.

    Graceful degradation:
      - EXA_API_KEY absent → empty suggestion list (HTTP 200, no 500).
      - Empty interests_md → empty suggestion list (HTTP 200, no 500).
    """
    from app.recommendations.service import SubscribedSource

    user = get_or_create_user(email, db)

    # Load existing subscriptions (name + normalised URL)
    rows = (
        db.query(Source.url, UserSourceAlias.display_name)
        .join(
            UserSourceAlias,
            (UserSourceAlias.source_id == Source.id)
            & (UserSourceAlias.user_id == user.id),
        )
        .all()
    )
    subscriptions = [
        SubscribedSource(name=display_name, url=url)
        for url, display_name in rows
    ]

    return suggestion_service.suggest(
        user_id=user.id,
        interests_md=user.interests_md,
        subscriptions=subscriptions,
        refresh=refresh,
    )
