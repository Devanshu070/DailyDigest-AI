import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import feedparser
import httpx

from app.ingestion.base import BaseIngester, ArticleData
from app.ingestion.youtube.resolver import resolve_channel_id, BROWSER_HEADERS
from app.ingestion.youtube.transcript import fetch_transcript
from app.ingestion.youtube.scraper import scrape_channel_videos

log = logging.getLogger(__name__)


class YouTubeIngester(BaseIngester):
    """
    Ingests videos published in the 24-hour window [run_at - 24h, run_at).

    run_at defaults to the current UTC time and should be shared across all
    sources in a single pipeline run so every channel uses the same cutoff.

    Accepts any of these as a source identifier:
      - Raw Channel ID:  UCxxxxxxxxxxxxxxxxxxxxxx
      - Channel URL:     https://www.youtube.com/channel/UCxxxxxxxxxxxxxxxxxxxxxx
      - Handle URL:      https://www.youtube.com/@lexfridman
      - Bare handle:     @lexfridman

    For each video in the window:
      1. Attempts to fetch a manual or auto-generated English transcript.
      2. Falls back to the RSS description if no English transcript is available.
    """

    def __init__(self, run_at: datetime | None = None, window_hours: int = 24):
        self.run_at: datetime = run_at or datetime.now(timezone.utc)
        self.window_start: datetime = self.run_at - timedelta(hours=window_hours)

    def resolve_channel_id(self, source_url: str) -> str:
        """Resolves any recognised YouTube identifier to a raw Channel ID (UC...)."""
        return resolve_channel_id(source_url)

    def _fetch_transcript(self, video_id: str) -> str:
        """
        Returns an English transcript for the video as a single string,
        or "" if no transcript is available.
        """
        return fetch_transcript(video_id)

    def _scrape_channel_videos(self, channel_id: str) -> list[dict[str, Any]]:
        """
        Fallback: fetches the channel's /videos page, parses ytInitialData,
        and returns a list of entry-like dicts compatible with parse().
        """
        return scrape_channel_videos(channel_id)

    def fetch(self, source_url: str) -> list[Any]:
        """
        Resolves the source URL to a Channel ID, fetches ALL entries from
        the RSS feed, and returns them unfiltered.

        Time-window filtering happens in parse() so the published_at of
        each entry can be evaluated against the window.

        Raises ValueError if the channel cannot be resolved or the feed
        is malformed.
        """
        channel_id = self.resolve_channel_id(source_url)
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        log.debug("Fetching YouTube RSS: %s", rss_url)

        # YouTube's RSS endpoint sometimes returns 404 or an HTML page (rate
        # limit / consent wall) when accessed with a generic user-agent.
        # Fetching via httpx with header rotation and retrying on transient
        # errors handles both cases.
        _RETRIES = 3
        _BACKOFF = [2, 5, 10]  # seconds between attempts
        _HEADERS_ROTATION = [
            None,                          # default httpx headers
            BROWSER_HEADERS,              # Chrome browser headers
            {"User-Agent": "curl/7.64.1"}, # curl user-agent
        ]
        last_exc: Exception | None = None
        feed_entries: list[Any] = []
        fetched_successfully = False

        for attempt in range(_RETRIES):
            try:
                headers = _HEADERS_ROTATION[attempt % len(_HEADERS_ROTATION)]
                response = httpx.get(rss_url, headers=headers, follow_redirects=True, timeout=15)
                response.raise_for_status()
                feed = feedparser.parse(response.content)
                if feed.bozo and not feed.entries:
                    raise ValueError(
                        f"feedparser could not parse RSS for channel {channel_id}: {feed.bozo_exception}"
                    )
                feed_entries = feed.entries
                fetched_successfully = True
                break
            except (httpx.HTTPStatusError, ValueError) as exc:
                last_exc = exc
                if attempt < _RETRIES - 1:
                    wait = _BACKOFF[attempt]
                    log.warning(
                        "RSS fetch attempt %d/%d failed for channel %s (%s). Retrying in %ds…",
                        attempt + 1, _RETRIES, channel_id, exc, wait,
                    )
                    time.sleep(wait)

        if not fetched_successfully:
            log.warning(
                "All %d RSS fetch attempts failed for channel %s. Falling back to scraping channel page. Error: %s",
                _RETRIES, channel_id, last_exc
            )
            feed_entries = self._scrape_channel_videos(channel_id)
            if not feed_entries:
                raise ValueError(
                    f"All {_RETRIES} RSS fetch attempts failed and page scraping fallback returned no videos for channel {channel_id}. Last error: {last_exc}"
                )

        log.debug("Returned %d entries for channel %s", len(feed_entries), channel_id)
        return feed_entries   # return all — parse() applies the time filter

    def parse(self, feed_entries: list[Any]) -> list[ArticleData]:
        """
        Filters feed entries to the collection window [window_start, run_at)
        and converts each qualifying entry into an ArticleData dict.

        The window is: videos published >= (run_at - 24h) AND < run_at.
        Videos published at or after run_at are excluded even if they appear
        in the feed — they belong to the next run.
        """
        import re
        scraped_at = datetime.now(timezone.utc)
        articles: list[ArticleData] = []

        for entry in feed_entries:
            # Skip YouTube Shorts
            link = entry.get("link", "")
            if "/shorts/" in link or "/shorts" in link:
                log.debug("Skipping '%s' — YouTube Shorts are excluded.", entry.get("title"))
                continue

            # Extract video ID
            video_id: str | None = entry.get("yt_videoid")
            if not video_id:
                m = re.search(r"v=([a-zA-Z0-9_-]+)", link)
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
                continue   # skip entries with unparseable dates

            # Time-window filter — the core of the new logic
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
