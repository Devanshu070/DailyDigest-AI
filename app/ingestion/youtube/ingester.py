import logging
from datetime import datetime, timedelta, timezone
from typing import Any
import re
import feedparser

from app.ingestion.base import BaseIngester, ArticleData
from app.ingestion.youtube.resolver import resolve_channel_id
from app.ingestion.youtube.transcript import fetch_transcript

log = logging.getLogger(__name__)


class YouTubeIngester(BaseIngester):
    def __init__(self, run_at: datetime | None = None):
        self.run_at: datetime = run_at or datetime.now(timezone.utc)
        self.window_start: datetime = self.run_at - timedelta(hours=24)

    def resolve_channel_id(self, source_url: str) -> str:
        return resolve_channel_id(source_url)

    def _fetch_transcript(self, video_id: str) -> str:
        return fetch_transcript(video_id)

    def fetch(self, source_url: str) -> list[Any]:
        channel_id = self.resolve_channel_id(source_url)
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

        log.debug("Fetching YouTube RSS: %s", rss_url)
        feed = feedparser.parse(rss_url)

        if feed.bozo and not feed.entries:
            raise ValueError(
                f"feedparser could not parse RSS for channel {channel_id}: {feed.bozo_exception}"
            )

        log.debug("RSS returned %d entries for channel %s", len(feed.entries), channel_id)
        return feed.entries

    def parse(self, feed_entries: list[Any]) -> list[ArticleData]:
        scraped_at = datetime.now(timezone.utc)
        articles: list[ArticleData] = []

        for entry in feed_entries:
            # Extract video ID
            video_id: str | None = entry.get("yt_videoid")
            if not video_id:
                m = re.search(r"v=([a-zA-Z0-9_-]+)", entry.get("link", ""))
                video_id = m.group(1) if m else None

            # Parse published date — must be timezone-aware for comparison
            try:
                raw_date = entry.get("published", "")
                published_at = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                log.warning(
                    "Could not parse published date for '%s' — skipping entry.",
                    entry.get("title"),
                )
                continue

            # Time-window filter
            if published_at < self.window_start:
                log.debug("Skipping '%s' — published before window (%s)", entry.get("title"), published_at)
                continue
            if published_at >= self.run_at:
                log.debug("Skipping '%s' — published after run_at cutoff (%s)", entry.get("title"), published_at)
                continue

            # Transcript → description fallback
            transcript = self._fetch_transcript(video_id) if video_id else ""
            description = entry.get("summary", "")

            if transcript:
                raw_content = transcript
                raw_content_source = "transcript"
                log.debug("Using transcript for '%s' (%d chars)", entry.get("title"), len(transcript))
            else:
                raw_content = description
                raw_content_source = "description"
                log.debug("Using description fallback for '%s'", entry.get("title"))

            articles.append(
                ArticleData(
                    title=entry.get("title", "Untitled"),
                    url=entry.get("link", ""),
                    raw_content=raw_content,
                    raw_content_source=raw_content_source,
                    published_at=published_at,
                    scraped_at=scraped_at,
                )
            )

        log.info(
            "Window [%s → %s): %d/%d entries kept",
            self.window_start.isoformat(),
            self.run_at.isoformat(),
            len(articles),
            len(feed_entries),
        )
        return articles
