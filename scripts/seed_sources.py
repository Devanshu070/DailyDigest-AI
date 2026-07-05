"""
scripts/seed_sources.py — Seeds the initial sources into the `sources` table.

Run once after `alembic upgrade head`:
    uv run python scripts/seed_sources.py

Safe to run multiple times — skips any source whose URL already exists.
"""

import sys
import os

# Ensure the project root is on sys.path so `app.*` imports resolve
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_db
from app.models import Source, SourceType

INITIAL_SOURCES = [
    # ── YouTube Channels ───────────────────────────────────────────────────
    {
        "name": "Lex Fridman",
        "type": SourceType.youtube,
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCSHZKyawb77ixDdsGog4iWA",
    },
    {
        "name": "Andrej Karpathy",
        "type": SourceType.youtube,
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCXUPKJO5MFQKMBGRJEOB3JQ",
    },
    {
        "name": "Yannic Kilcher",
        "type": SourceType.youtube,
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCZHmQk67mSJgfCCTn7xBfew",
    },
    # ── Blogs / Newsletters ────────────────────────────────────────────────
    {
        "name": "OpenAI Blog",
        "type": SourceType.blog,
        "url": "https://openai.com/news/rss.xml",
    },
    {
        "name": "Anthropic Blog",
        "type": SourceType.blog,
        "url": "https://www.anthropic.com/rss.xml",
    },
    {
        "name": "Google DeepMind Blog",
        "type": SourceType.blog,
        "url": "https://deepmind.google/blog/rss.xml",
    },
    {
        "name": "Hugging Face Blog",
        "type": SourceType.blog,
        "url": "https://huggingface.co/blog/feed.xml",
    },
]


def seed() -> None:
    with get_db() as db:
        added = 0
        skipped = 0

        for data in INITIAL_SOURCES:
            existing = db.query(Source).filter_by(url=data["url"]).first()
            if existing:
                print(f"  SKIP  {data['name']} (already exists)")
                skipped += 1
                continue

            source = Source(
                name=data["name"],
                type=data["type"],
                url=data["url"],
                is_active=True,
            )
            db.add(source)
            print(f"  ADD   {data['name']} ({data['type'].value})")
            added += 1

    print(f"\nDone. {added} sources added, {skipped} skipped.")


if __name__ == "__main__":
    seed()
