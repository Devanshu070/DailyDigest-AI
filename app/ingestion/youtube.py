# %%

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, TypedDict

import feedparser
import httpx
from app.ingestion.base import BaseIngester

log = logging.getLogger(__name__)

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound
    HAS_TRANSCRIPT_API = True
except ImportError:
    HAS_TRANSCRIPT_API = False


class ArticleData(TypedDict):
    title: str
    url: str
    raw_content: str          # Full transcript text, or description as fallback
    raw_content_source: str   # "transcript" | "description" — tracks which was used
    published_at: datetime
    scraped_at: datetime


# Regex matching a bare YouTube Channel ID
_CHANNEL_ID_RE = re.compile(r"^UC[a-zA-Z0-9_-]{22}$")

# Headers that mimic a real browser — needed to resolve channel handles
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


class YouTubeIngester(BaseIngester):
    """
    Ingests videos published in the 24-hour window ending at `run_at`.

    The collection window is: [run_at - 24h, run_at)
      - Videos published before (run_at - 24h) are too old — excluded.
      - Videos published at or after run_at are too new — excluded.
        This includes anything uploaded while the pipeline is running;
        they will be picked up in the next day's run.

    `run_at` should be set once per pipeline execution and shared across
    all sources so every channel is filtered against the same cutoff.
    It defaults to the current UTC time when the ingester is instantiated.

    Accepts any of the following as a source identifier stored in `sources.url`:
      - Raw Channel ID:   UCxxxxxxxxxxxxxxxxxxxxxx
      - Channel URL:      https://www.youtube.com/channel/UCxxxxxxxxxxxxxxxxxxxxxx
      - Handle URL:       https://www.youtube.com/@lexfridman
      - Bare handle:      @lexfridman

    For each video in the window:
      1. Attempts to fetch a manual or auto-generated English transcript.
      2. Falls back to the RSS description if no English transcript is available.
    """

    def __init__(self, run_at: datetime | None = None):
        # Snapshot the cutoff once. All sources in this run share the same window.
        self.run_at: datetime = run_at or datetime.now(timezone.utc)
        self.window_start: datetime = self.run_at - timedelta(hours=24)

    # ------------------------------------------------------------------
    # Channel ID resolution
    # ------------------------------------------------------------------

    def resolve_channel_id(self, source_url: str) -> str:
        """
        Resolves any recognised YouTube identifier to a raw Channel ID (UC...).
        Raises ValueError if resolution fails.
        """
        identifier = source_url.strip()

        # Already a channel ID — nothing to do
        if _CHANNEL_ID_RE.match(identifier):
            return identifier

        # Direct channel URL: .../channel/UC...
        m = re.search(r"youtube\.com/channel/(UC[a-zA-Z0-9_-]{22})", identifier)
        if m:
            return m.group(1)

        # Handle embedded in a full URL: .../@handle
        m = re.search(r"youtube\.com/(@[a-zA-Z0-9_\-\.]+)", identifier)
        if m:
            identifier = m.group(1)   # reduce to bare handle for page fetch

        # Build the page URL to scrape the channel ID from
        page_url = (
            f"https://www.youtube.com/{identifier}"
            if identifier.startswith("@")
            else f"https://www.youtube.com/c/{identifier}"
        )

        log.debug("Resolving channel ID via page fetch: %s", page_url)

        try:
            response = httpx.get(page_url, headers=_BROWSER_HEADERS, follow_redirects=True, timeout=15)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ValueError(f"HTTP error while resolving channel page: {exc}") from exc

        html = response.text

        # Three extraction strategies, in preference order
        for pattern in [
            r'<meta itemprop="channelId" content="(UC[a-zA-Z0-9_-]{22})"',
            r'"externalId"\s*:\s*"(UC[a-zA-Z0-9_-]{22})"',
            r'youtube\.com/feeds/videos\.xml\?channel_id=(UC[a-zA-Z0-9_-]{22})',
        ]:
            m = re.search(pattern, html)
            if m:
                return m.group(1)

        raise ValueError(
            f"Could not extract Channel ID from page: {page_url}. "
            "The channel may be private, renamed, or the page structure may have changed."
        )

    # ------------------------------------------------------------------
    # Transcript fetching
    # ------------------------------------------------------------------

    def _fetch_transcript(self, video_id: str) -> str:
        """
        Fetches an English transcript for a given video ID.

        Tries, in order:
          1. Manually created English transcript (en, en-US, en-GB, en-IN)
          2. Auto-generated English transcript   (en, en-US, en-GB, en-IN)

        If neither is available the method returns "" and the caller
        falls back to the RSS description. Non-English transcripts are
        intentionally ignored.

        Returns the full transcript as a single string, or "" on failure.
        """
        if not HAS_TRANSCRIPT_API:
            log.warning("youtube-transcript-api not installed — transcripts unavailable.")
            return ""

        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

            # English-only: manual first, then auto-generated
            for fetch_fn in [
                lambda tl: tl.find_manually_created_transcript(["en", "en-US", "en-GB","en-IN"]),
                lambda tl: tl.find_generated_transcript(["en", "en-US", "en-GB","en-IN"]),
            ]:
                try:
                    transcript = fetch_fn(transcript_list).fetch()
                    return "\n".join(segment["text"] for segment in transcript)
                except Exception:
                    continue

            log.debug("No English transcript available for video %s — falling back to description", video_id)

        except TranscriptsDisabled:
            log.debug("Transcripts disabled for video %s", video_id)
        except NoTranscriptFound:
            log.debug("No transcript found for video %s", video_id)
        except Exception as exc:
            log.warning("Unexpected error fetching transcript for %s: %s", video_id, exc)

        return ""

    # ------------------------------------------------------------------
    # BaseIngester interface
    # ------------------------------------------------------------------

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
        feed = feedparser.parse(rss_url)

        if feed.bozo and not feed.entries:
            raise ValueError(
                f"feedparser could not parse RSS for channel {channel_id}: {feed.bozo_exception}"
            )

        log.debug("RSS returned %d entries for channel %s", len(feed.entries), channel_id)
        return feed.entries   # return all — parse() applies the time filter

    def parse(self, feed_entries: list[Any]) -> list[ArticleData]:
        """
        Filters feed entries to the collection window [window_start, run_at)
        and converts each qualifying entry into an ArticleData dict.

        The window is: videos published >= (run_at - 24h) AND < run_at.
        Videos published at or after run_at are excluded even if they appear
        in the feed — they belong to the next run.
        """
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


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)-8s %(name)s — %(message)s",
    )

    # Usage: python -m app.ingestion.youtube [@handle] [run_at_iso]
    # run_at_iso example: 2025-05-21T06:00:00+00:00
    source = "@bytemonk"
    if len(sys.argv) > 1 and not sys.argv[1].startswith(("-f=", "--f=")):
        source = sys.argv[1]

    run_at: datetime | None = None
    if len(sys.argv) > 2:
        try:
            run_at = datetime.fromisoformat(sys.argv[2])
            if run_at.tzinfo is None:
                run_at = run_at.replace(tzinfo=timezone.utc)
        except ValueError:
            print(f"[WARN] Could not parse run_at '{sys.argv[2]}' — using current UTC time.", file=sys.stderr)

    ingester = YouTubeIngester(run_at=run_at)

    try:
        entries = ingester.fetch(source)
        articles = ingester.parse(entries)
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    if not articles:
        print(f"No videos published in the last 24 hours for {source}.")
    else:
        for art in articles:
            print(
                f"{art['title']} | {art['url']} | "
                f"{art['published_at'].isoformat()} | "
                f"{art['raw_content_source']} | {len(art['raw_content'])} chars"
            )
# %%
