import logging
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from app.ingestion.base import BaseIngester, ArticleData
from app.ingestion.blog.fetcher import fetch_rss, scrape_html_article, scrape_blog_index

log = logging.getLogger(__name__)


class BlogIngester(BaseIngester):
    """
    Ingests blog and newsletter articles published within a configurable
    time window [run_at - window_hours, run_at).

    Accepts any of these as a source identifier:
      - RSS/Atom feed URL:   https://openai.com/news/rss.xml
      - Blog base URL:       https://openai.com/news  (feed auto-discovered via trafilatura)
      - Direct article URL:  https://example.com/posts/my-article  (scraped directly)

    For each article in the window:
      1. Attempts to fetch full article text via trafilatura HTML extraction.
      2. Falls back to the RSS summary/description if HTML extraction yields nothing.
    """

    def __init__(self, run_at: datetime | None = None, window_hours: int = 24):
        self.run_at: datetime = run_at or datetime.now(timezone.utc)
        self.window_start: datetime = self.run_at - timedelta(hours=window_hours)

    # ------------------------------------------------------------------
    # BaseIngester interface
    # ------------------------------------------------------------------

    def fetch(self, source_url: str) -> list[Any]:
        """
        Fetches raw entries from source_url using the best available strategy:

          1. RSS/Atom feed (preferred) — returns feedparser entry dicts.
          2. trafilatura feed discovery + blog index scrape (fallback) — when
             the URL is a blog homepage rather than a direct feed URL.

        Time-window filtering happens in parse(), not here, so that all
        published_at values can be evaluated consistently.

        Raises ValueError if no entries could be obtained by any strategy.
        """
        log.debug("BlogIngester.fetch: %s", source_url)

        # --- Strategy 1: try RSS directly ---
        entries = fetch_rss(source_url)
        if entries:
            log.info("RSS fetch returned %d entries for %s", len(entries), source_url)
            return entries

        # --- Strategy 2: trafilatura feed discovery + index scrape ---
        log.info(
            "RSS unavailable for %s — trying blog index / feed discovery.", source_url
        )
        entries = scrape_blog_index(source_url)
        if entries:
            log.info(
                "Blog index scrape returned %d entries for %s",
                len(entries),
                source_url,
            )
            return entries

        raise ValueError(
            f"Could not fetch any articles from {source_url}. "
            "Both RSS and HTML scraping strategies returned nothing."
        )

    def parse(self, raw_entries: list[Any]) -> list[ArticleData]:
        """
        Filters entries to the time window [window_start, run_at) and converts
        each qualifying entry to an ArticleData dict.

        For each entry the raw_content is populated as follows:
          1. Full article text extracted by trafilatura (preferred).
          2. RSS summary / description (fallback).
        """
        scraped_at = datetime.now(timezone.utc)
        articles: list[ArticleData] = []

        for entry in raw_entries:
            url = entry.get("link", "")
            title = entry.get("title", "Untitled")

            # --- Parse published date ---
            published_at = self._parse_published(entry)
            if published_at is None:
                # Entries without a parseable date are treated as "just now" so
                # they are included in the current window — better to include a
                # borderline article than to silently drop it.
                log.debug(
                    "No parseable date for '%s' — including in current window.", title
                )
                published_at = scraped_at

            # --- Time-window filter ---
            if published_at < self.window_start:
                log.debug(
                    "Skipping '%s' — published before window (%s)", title, published_at
                )
                continue
            if published_at >= self.run_at:
                log.debug(
                    "Skipping '%s' — published after run_at cutoff (%s)",
                    title,
                    published_at,
                )
                continue

            # --- Content: trafilatura → RSS summary fallback ---
            # If the entry already carries pre-scraped text (blog index fallback
            # path), reuse it directly instead of re-fetching.
            pre_scraped = entry.get("content_text", "")
            if pre_scraped:
                raw_content = pre_scraped
                raw_content_source = "html_scrape"
                log.debug(
                    "Reusing pre-scraped content for '%s' (%d chars)", title, len(raw_content)
                )
            elif url:
                html_text = scrape_html_article(url)
                if html_text:
                    raw_content = html_text
                    raw_content_source = "html_scrape"
                    log.debug(
                        "trafilatura extracted %d chars for '%s'",
                        len(html_text),
                        title,
                    )
                else:
                    raw_content = self._rss_summary(entry)
                    raw_content_source = "rss_summary"
                    log.debug("Using RSS summary fallback for '%s'", title)
            else:
                raw_content = self._rss_summary(entry)
                raw_content_source = "rss_summary"
                log.debug("No URL available for '%s' — using RSS summary", title)

            if not raw_content.strip():
                log.warning("No content available for '%s' (%s) — skipping.", title, url)
                continue

            articles.append(
                ArticleData(
                    title=title,
                    url=url,
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
            len(raw_entries),
        )
        return articles

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_published(self, entry: dict[str, Any]) -> datetime | None:
        """
        Tries multiple date fields that RSS / Atom feeds commonly use and
        returns a timezone-aware datetime, or None if nothing parses.
        """
        for field in ("published", "updated", "created"):
            raw = entry.get(field, "")
            if not raw:
                continue
            try:
                # ISO 8601 (e.g. Atom feeds)
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except (ValueError, AttributeError):
                pass
            try:
                # RFC 2822 (e.g. RSS 2.0 feeds)
                dt = parsedate_to_datetime(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                pass

        # feedparser sometimes pre-parses dates into a struct_time tuple
        for field in ("published_parsed", "updated_parsed"):
            parsed = entry.get(field)
            if parsed:
                try:
                    dt = datetime(*parsed[:6], tzinfo=timezone.utc)
                    return dt
                except Exception:
                    pass

        return None

    @staticmethod
    def _rss_summary(entry: dict[str, Any]) -> str:
        """Returns the richest summary text available from the entry dict."""
        # feedparser puts the full <content> here when present
        content_list = entry.get("content", [])
        if content_list:
            return content_list[0].get("value", "")
        return entry.get("summary", "")
