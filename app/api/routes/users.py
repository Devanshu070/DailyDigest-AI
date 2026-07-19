"""
app/api/routes/users.py — User preferences and settings.

GET   /api/v1/users/me                 → Fetch user profile (digest_time, interests, etc)
PATCH /api/v1/users/me/digest-time     → Update daily delivery time
PATCH /api/v1/users/me/interests       → Update Markdown interest prompt
PATCH /api/v1/users/me/digest-pause    → Pause or resume scheduled digest delivery
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db_session
from app.models import User
from app.schemas import (
    UserDigestPauseUpdate,
    UserDigestTimeUpdate,
    UserInterestsUpdate,
    UserResponse,
)

import logging

log = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["Users"])


def get_or_create_user(email: str, db: Session) -> User:
    """Fetch an active user by email, or auto-create one on first login."""
    user = db.query(User).filter_by(email=email, is_active=True).first()
    if not user:
        log.info("Auto-creating user for first-time login: %s", email)
        user = User(email=email)
        db.add(user)
        db.flush()  # assigns the PK without committing the outer transaction
    return user


@router.get("/me", response_model=UserResponse)
def get_user_profile(
    email: str = Query(..., description="User email"),
    db: Session = Depends(get_db_session)
):
    """Get the user's current preferences (digest time, interests, etc)."""
    return get_or_create_user(email, db)


@router.patch("/me/digest-time", response_model=UserResponse)
def update_digest_time(
    body: UserDigestTimeUpdate,
    email: str = Query(..., description="User email"),
    db: Session = Depends(get_db_session)
):
    """Update the UTC time when this user receives their daily digest."""
    user = get_or_create_user(email, db)
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
    user = get_or_create_user(email, db)
    user.interests_md = body.interests_md
    db.flush()
    return user


@router.patch("/me/digest-pause", response_model=UserResponse)
def update_digest_pause(
    body: UserDigestPauseUpdate,
    email: str = Query(..., description="User email"),
    db: Session = Depends(get_db_session),
):
    """Pause or resume scheduled digest delivery for this user."""
    user = get_or_create_user(email, db)
    user.digest_paused = body.paused
    db.flush()
    return user
