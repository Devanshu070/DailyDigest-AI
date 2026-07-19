"""Authentication dependencies for protected destructive operations."""

from fastapi import Header, HTTPException, status
from google.auth.transport import requests
from google.oauth2 import id_token

from app.config import settings


def get_current_firebase_user(
    authorization: str | None = Header(default=None),
) -> dict:
    """Verify a Firebase bearer token using Google's public signing keys."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid Firebase bearer token is required.",
        )
    if not settings.firebase_project_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Account management is not configured on the server.",
        )

    token = authorization.removeprefix("Bearer ").strip()
    try:
        return id_token.verify_firebase_token(
            token,
            requests.Request(),
            audience=settings.firebase_project_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The Firebase session is invalid or expired.",
        ) from exc
