"""
scripts/seed_user.py — Seeds the default user and subscribes them to all active sources.

Run after `alembic upgrade head` and `seed_sources.py`:
    uv run python scripts/seed_user.py

Safe to run multiple times — idempotent (skips if user/subscriptions already exist).
Reads email from DIGEST_RECIPIENT_EMAIL env/settings.
Reads interests from app/prompts/user_interests.md.
Sets digest_time to match the cron schedule in .github/workflows/daily_digest.yml.
"""


import argparse
import sys
import os
from datetime import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_db
from app.models import Source, User
from app.config import settings

_INTERESTS_PATH = Path(__file__).parent.parent / "app" / "prompts" / "user_interests.md"


def seed(email: str | None = None) -> None:
    email = email or settings.digest_recipient_email
    print(f"  Using email: {email!r}")
    # Load interests from the static file
    if _INTERESTS_PATH.exists():
        interests_md = _INTERESTS_PATH.read_text(encoding="utf-8").strip()
        print(f"  Loaded interests from {_INTERESTS_PATH.name} ({len(interests_md)} chars)")
    else:
        interests_md = (
            "Interested in AI research, machine learning, technology trends, "
            "and software engineering. Prioritize technical depth and novel insights."
        )
        print("  WARNING: user_interests.md not found — using generic fallback.")

    # Digest time from settings (extracted from cron schedule)
    digest_time = time(
        settings.pipeline_run_hour_utc,
        settings.pipeline_run_minute_utc,
    )

    with get_db() as db:
        # Upsert user
        user = db.query(User).filter_by(email=email).first()
        if user:
            print(f"  SKIP  User {email!r} already exists (id={user.id})")
        else:
            user = User(
                email=email,
                interests_md=interests_md,
                digest_time=digest_time,
                is_active=True,
                source_ids=[],
            )
            db.add(user)
            db.flush()
            print(f"  ADD   User {email!r} (digest_time={digest_time}, id={user.id})")

        # Subscribe user to all active sources
        all_sources = db.query(Source).filter_by(is_active=True).all()
        
        # Ensure source_ids is a list (could be None on old records)
        current_source_ids = user.source_ids or []
        new_source_ids = list(current_source_ids)
        
        added = 0
        skipped = 0
        for source in all_sources:
            if source.id in new_source_ids:
                skipped += 1
            else:
                new_source_ids.append(source.id)
                added += 1
                print(f"  SUB   {source.name} ({source.type.value})")

        if added > 0:
            # Reassign to trigger SQLAlchemy mutation tracking
            user.source_ids = new_source_ids

    print(f"\nDone. {added} subscription(s) added, {skipped} already existed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed a user into the DailyDigest database.")
    parser.add_argument(
        "--email",
        type=str,
        default=None,
        help="Email address of the user to create. Defaults to DIGEST_RECIPIENT_EMAIL from .env.",
    )
    args = parser.parse_args()
    seed(email=args.email)