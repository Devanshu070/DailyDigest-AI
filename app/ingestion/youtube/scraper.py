import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from app.ingestion.youtube.resolver import BROWSER_HEADERS

log = logging.getLogger(__name__)


def scrape_channel_videos(channel_id: str) -> list[dict[str, Any]]:
    """
    Fallback: fetches the channel's /videos page, parses ytInitialData,
    and returns a list of entry-like dicts compatible with parse().
    """
    url = f"https://www.youtube.com/channel/{channel_id}/videos"
    log.info("Scraping channel videos fallback from: %s", url)

    try:
        response = httpx.get(url, headers=BROWSER_HEADERS, follow_redirects=True, timeout=15)
        response.raise_for_status()
    except Exception as exc:
        log.warning("Failed to fetch channel videos page for %s: %s", channel_id, exc)
        return []

    html = response.text
    m = re.search(r"var ytInitialData = ({.*?});", html)
    if not m:
        log.warning("Could not find ytInitialData in channel videos HTML page for %s", channel_id)
        return []

    try:
        data = json.loads(m.group(1))
    except Exception as exc:
        log.warning("Failed to parse ytInitialData JSON for %s: %s", channel_id, exc)
        return []

    try:
        contents = (
            data.get("contents", {})
            .get("twoColumnBrowseResultsRenderer", {})
            .get("tabs", [])[1]
            .get("tabRenderer", {})
            .get("content", {})
            .get("richGridRenderer", {})
            .get("contents", [])
        )
    except (KeyError, IndexError, TypeError) as exc:
        log.warning("Failed to navigate ytInitialData tabs structure for %s: %s", channel_id, exc)
        contents = []

    fake_entries: list[dict[str, Any]] = []
    base_time = datetime.now(timezone.utc)

    for content in contents:
        if "richItemRenderer" not in content:
            continue
        item = content["richItemRenderer"].get("content", {}).get("lockupViewModel")
        if not item:
            continue

        video_id = item.get("contentId")
        if not video_id:
            continue

        metadata = item.get("metadata", {}).get("lockupMetadataViewModel", {})
        title = metadata.get("title", {}).get("content", "Untitled")

        # Extract relative published text
        rows = metadata.get("metadata", {}).get("contentMetadataViewModel", {}).get("metadataRows", [])
        published_text = ""
        for row in rows:
            for part in row.get("metadataParts", []):
                text = part.get("text", {}).get("content", "")
                if "ago" in text or "streamed" in text or "yesterday" in text.lower():
                    published_text = text
                    break

        # Convert relative time string to approximate ISO date
        published_iso = parse_relative_time(published_text, base_time)

        fake_entries.append({
            "yt_videoid": video_id,
            "title": title,
            "link": f"https://www.youtube.com/watch?v={video_id}",
            "published": published_iso,
            "summary": "",  # No summary/description on page, fallback to transcript or blank
        })

    log.debug("Scrape returned %d entries for channel %s", len(fake_entries), channel_id)
    return fake_entries


def parse_relative_time(relative_str: str, base_time: datetime) -> str:
    """
    Parses relative time strings like '1 day ago', '3 hours ago', '1 week ago'
    into an ISO formatted timestamp relative to base_time.
    """
    s = relative_str.lower().strip()
    delta = timedelta()

    # Regex to match: [number] [unit] ago
    m = re.search(r"(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago", s)
    if m:
        val = int(m.group(1))
        unit = m.group(2)
        if unit == "second":
            delta = timedelta(seconds=val)
        elif unit == "minute":
            delta = timedelta(minutes=val)
        elif unit == "hour":
            delta = timedelta(hours=val)
        elif unit == "day":
            # For '1 day ago', we map to 23 hours ago so it falls within a 24-hour window
            if val == 1:
                delta = timedelta(hours=23)
            else:
                delta = timedelta(days=val)
        elif unit == "week":
            delta = timedelta(weeks=val)
        elif unit == "month":
            delta = timedelta(days=val * 30)
        elif unit == "year":
            delta = timedelta(days=val * 365)
    elif "yesterday" in s:
        delta = timedelta(hours=23)  # Use 23 hours so it falls within the 24-hour window

    dt = base_time - delta
    return dt.isoformat().replace("+00:00", "Z")
