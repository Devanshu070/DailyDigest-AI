"""
app/api/routes/articles.py — Read-only article endpoints (user-scoped).

GET /api/v1/articles        → List articles for a user's subscribed sources
GET /api/v1/articles/{id}   → Full article detail including content
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db_session
from app.models import Article, ProcessingStatus, User, UserSourceAlias
from app.schemas import ArticleListItem, ArticleResponse

router = APIRouter(prefix="/articles", tags=["Articles"])


def _get_user_source_ids(email: str, db: Session) -> list:
    """Resolve a user's subscribed source IDs or raise 404."""
    user = db.query(User).filter_by(email=email, is_active=True).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User '{email}' not found")
    rows = db.query(UserSourceAlias.source_id).filter_by(user_id=user.id).all()
    return [r[0] for r in rows]


@router.get("", response_model=list[ArticleListItem])
def list_articles(
    email: str = Query(..., description="User email to scope results to"),
    processing_status: Optional[ProcessingStatus] = Query(None, description="Filter by processing status"),
    limit: int = Query(50, ge=1, le=500, description="Max number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db: Session = Depends(get_db_session),
):
    """List articles belonging to a user's subscribed sources."""
    source_ids = _get_user_source_ids(email, db)

    if not source_ids:
        return []

    query = db.query(Article).filter(Article.source_id.in_(source_ids))

    if processing_status:
        query = query.filter(Article.processing_status == processing_status)

    return query.order_by(Article.published_at.desc()).offset(offset).limit(limit).all()


@router.get("/{article_id}", response_model=ArticleResponse)
def get_article(
    article_id: uuid.UUID,
    email: str = Query(..., description="User email to validate ownership"),
    db: Session = Depends(get_db_session)
):
    """Get a single article's summary and link (verifies user is subscribed to its source)."""
    source_ids = _get_user_source_ids(email, db)
    if not source_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
        
    article = db.query(Article).filter(
        Article.id == article_id,
        Article.source_id.in_(source_ids)
    ).first()
    
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return article
