"""
fetcher.py — low-level fetch helpers for the blog ingester.

Two strategies, tried in order:
  1. RSS/Atom feed via feedparser  — preferred; most major blogs publish one
  2. HTML scraping via trafilatura  — fallback when no usable RSS feed exists

Both return a list of raw entry dicts that BlogIngester.parse() understands.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any

import feedparser
import httpx

log = logging.getLogger(__name__)

# Browser-like headers — reduces the chance of getting blocked by Cloudflare /
# anti-bot measures on plain HTML pages.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_RETRIES = 3
_BACKOFF = [2, 5, 10]  # seconds between attempts


# ---------------------------------------------------------------------------
# Strategy 1 — RSS / Atom via feedparser
# ---------------------------------------------------------------------------

def fetch_rss(feed_url: str) -> list[dict[str, Any]]:
    """
    Fetches and parses an RSS/Atom feed at feed_url.

    Returns a list of feedparser entry dicts, or [] on failure.
    Each entry has at minimum: title, link, published/updated, summary.
    """
    last_exc: Exception | None = None

    for attempt in range(_RETRIES):
        try:
            response = httpx.get(
                feed_url,
                headers=BROWSER_HEADERS,
                follow_redirects=True,
                timeout=15,
            )
            response.raise_for_status()
            feed = feedparser.parse(response.content)

            if feed.bozo and not feed.entries:
                raise ValueError(
                    f"feedparser could not parse feed at {feed_url}: "
                    f"{feed.bozo_exception}"
                )

            log.debug(
                "RSS fetch succeeded for %s — %d entries", feed_url, len(feed.entries)
            )
            return feed.entries

        except (httpx.HTTPError, ValueError) as exc:
            last_exc = exc
            if attempt < _RETRIES - 1:
                wait = _BACKOFF[attempt]
                log.warning(
                    "RSS fetch attempt %d/%d failed for %s (%s). Retrying in %ds…",
                    attempt + 1,
                    _RETRIES,
                    feed_url,
                    exc,
                    wait,
                )
                time.sleep(wait)

    log.warning(
        "All %d RSS fetch attempts failed for %s. Last error: %s",
        _RETRIES,
        feed_url,
        last_exc,
    )
    return []


# ---------------------------------------------------------------------------
# Strategy 2 — HTML scraping via trafilatura
# ---------------------------------------------------------------------------

def scrape_html_article(url: str) -> str:
    """
    Downloads a single article page and extracts its main text content
    using trafilatura.

    Returns the extracted text, or "" if extraction fails.
    """
    try:
        import trafilatura
    except ImportError:
        log.warning("trafilatura not installed — HTML scraping unavailable.")
        return ""

    try:
        response = httpx.get(
            url,
            headers=BROWSER_HEADERS,
            follow_redirects=True,
            timeout=20,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("Failed to download article page %s: %s", url, exc)
        return ""

    text = trafilatura.extract(
        response.text,
        include_comments=False,
        include_tables=False,
        no_fallback=False,
    )
    if not text:
        log.debug("trafilatura returned no content for %s", url)
        return ""

    log.debug("trafilatura extracted %d chars from %s", len(text), url)
    return text


def scrape_blog_index(base_url: str) -> list[dict[str, Any]]:
    """
    Last-resort fallback: fetches the blog's index / landing page and
    uses trafilatura's feed discovery to locate article links, then
    scrapes each one individually.

    Returns a list of minimal entry dicts compatible with BlogIngester.parse():
      { "title": str, "link": str, "published": str|None, "content_text": str }
    """
    try:
        import trafilatura
        from trafilatura.feeds import find_feed_urls
    except ImportError:
        log.warning("trafilatura not installed — blog index scraping unavailable.")
        return []

    log.info("Attempting blog index scrape for: %s", base_url)

    # Try to auto-discover an RSS feed first
    try:
        discovered_feeds = find_feed_urls(base_url)
    except Exception as exc:
        log.warning("Feed discovery failed for %s: %s", base_url, exc)
        discovered_feeds = []

    if discovered_feeds:
        log.info(
            "trafilatura discovered %d feed(s) at %s — trying first: %s",
            len(discovered_feeds),
            base_url,
            discovered_feeds[0],
        )
        entries = fetch_rss(discovered_feeds[0])
        if entries:
            return entries

    # No RSS found — scrape the index page for links
    try:
        response = httpx.get(
            base_url,
            headers=BROWSER_HEADERS,
            follow_redirects=True,
            timeout=15,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("Failed to fetch blog index %s: %s", base_url, exc)
        return []

    # Use trafilatura to extract links from the index page
    try:
        links = trafilatura.extract_metadata(response.text, default_url=base_url)
        # trafilatura.extract_links is available in newer versions
        from trafilatura.utils import filter_urls
        article_links = filter_urls(
            trafilatura.extract_links(response.text, base_url=base_url) or [],
            base_url,
        )
    except Exception as exc:
        log.warning("Could not extract links from index page %s: %s", base_url, exc)
        return []

    entries: list[dict[str, Any]] = []
    scraped_at_iso = datetime.now(timezone.utc).isoformat()

    for link in article_links[:20]:  # cap at 20 to avoid runaway scraping
        content = scrape_html_article(link)
        if not content:
            continue
        entries.append(
            {
                "title": link,          # title will be overridden by parser if richer data found
                "link": link,
                "published": None,      # unknown — parser will use scraped_at as fallback
                "content_text": content,
            }
        )

    log.debug(
        "Blog index scrape returned %d articles for %s", len(entries), base_url
    )
    return entries
