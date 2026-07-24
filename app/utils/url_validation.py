"""
app/utils/url_validation.py — Reusable URL normalisation and validation utilities.

Used by:
  - app/api/routes/sources.py    (source creation)
  - app/utils/suggestion_validation.py  (suggestion post-processing)

All functions are pure and stateless.
"""

from typing import TypeVar, Callable
from urllib.parse import urlparse, urlunparse

T = TypeVar("T")


def normalize_url(raw: str) -> str:
    """
    Canonicalize a URL so equivalent inputs map to a single source record.

    Rules:
      - Strip surrounding whitespace
      - Lowercase scheme and host
      - Strip leading 'www.'
      - Strip trailing slash from path
      - Preserve query string and fragment as-is

    Examples:
      >>> normalize_url("https://WWW.Example.com/blog/")
      'https://example.com/blog'
      >>> normalize_url("http://www.youtube.com/@channel")
      'http://youtube.com/@channel'
    """
    parsed = urlparse(raw.strip())
    scheme = (parsed.scheme or "https").lower()
    netloc = (parsed.netloc or parsed.path).lower()

    # Use startswith to strip exactly "www." — lstrip would incorrectly strip
    # any leading combination of 'w' and '.' characters.
    if netloc.startswith("www."):
        netloc = netloc[4:]

    host = netloc
    path = parsed.path.rstrip("/") if parsed.netloc else ""
    return urlunparse((scheme, host, path, parsed.params, parsed.query, parsed.fragment))


def is_valid_url(url: str) -> bool:
    """
    Return True if *url* is a well-formed http/https URL.

    Checks:
      - Scheme must be 'http' or 'https'
      - Hostname must be present and non-empty
      - No whitespace in netloc

    Args:
        url: The URL string to validate.

    Returns:
        True if the URL passes all checks, False otherwise.
    """
    try:
        parsed = urlparse(url)
        return (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and not any(c.isspace() for c in parsed.netloc)
        )
    except Exception:
        return False


def deduplicate_by_url(items: list[T], key_fn: Callable[[T], str]) -> list[T]:
    """
    Remove duplicates from *items*, keeping the first occurrence of each
    normalised URL.

    Args:
        items:  Any list of objects.
        key_fn: A callable that extracts a raw URL string from each item.
                The URL is normalised before comparison so that equivalent
                variants (e.g. trailing slash, www prefix) are treated as
                the same.

    Returns:
        A new list preserving insertion order, with duplicates removed.

    Example:
        >>> deduplicate_by_url(
        ...     [{"url": "https://www.example.com/"}, {"url": "https://example.com"}],
        ...     key_fn=lambda x: x["url"],
        ... )
        [{"url": "https://www.example.com/"}]
    """
    seen: set[str] = set()
    result: list[T] = []
    for item in items:
        canonical = normalize_url(key_fn(item))
        if canonical not in seen:
            seen.add(canonical)
            result.append(item)
    return result
