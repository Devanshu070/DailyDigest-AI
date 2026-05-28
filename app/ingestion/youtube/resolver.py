import logging
import re
import httpx
from app.ingestion.youtube.constants import CHANNEL_ID_RE, BROWSER_HEADERS

log = logging.getLogger(__name__)


def resolve_channel_id(source_url: str) -> str:
    """Resolves any recognised YouTube identifier to a raw Channel ID (UC...)."""
    identifier = source_url.strip()

    # Already a channel ID — nothing to do
    if CHANNEL_ID_RE.match(identifier):
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
        response = httpx.get(page_url, headers=BROWSER_HEADERS, follow_redirects=True, timeout=15)
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
