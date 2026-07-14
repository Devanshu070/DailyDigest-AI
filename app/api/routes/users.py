"""
app/api/routes/users.py — User preferences and settings.

GET   /api/v1/users/me                 → Fetch user profile (digest_time, interests, etc)
PATCH /api/v1/users/me/digest-time     → Update daily delivery time
PATCH /api/v1/users/me/interests       → Update Markdown interest prompt
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db_session
from app.models import User
from app.schemas import UserDigestTimeUpdate, UserInterestsUpdate, UserResponse

router = APIRouter(prefix="/users", tags=["Users"])


def _get_user(email: str, db: Session) -> User:
    """Fetch an active user by email or raise 404."""
    user = db.query(User).filter_by(email=email, is_active=True).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User '{email}' not found")
    return user


@router.get("/me", response_model=UserResponse)
def get_user_profile(
    email: str = Query(..., description="User email"),
    db: Session = Depends(get_db_session)
):
    """Get the user's current preferences (digest time, interests, etc)."""
    return _get_user(email, db)


@router.patch("/me/digest-time", response_model=UserResponse)
def update_digest_time(
    body: UserDigestTimeUpdate,
    email: str = Query(..., description="User email"),
    db: Session = Depends(get_db_session)
):
    """Update the UTC time when this user receives their daily digest."""
    user = _get_user(email, db)
    user.digest_time = body.digest_time
    db.flush()
    return user


@router.patch("/me/interests", response_model=UserResponse)
def update_interests(
    body: UserInterestsUpdate,
    email: str = Query(..., description="User email"),
    db: Session = Depends(get_db_session)
):
    """Update the custom Markdown prompt used to personalize this user's digest."""
    user = _get_user(email, db)
    user.interests_md = body.interests_md
    db.flush()
    return user
