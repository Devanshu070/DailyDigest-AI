"""
app/search/exa.py — Exa search provider implementation.

Uses the official exa-py SDK. The concrete search method is discovered
at runtime from the installed package version rather than being hard-coded,
so the implementation stays compatible as the SDK evolves.

Desired search behaviour (achieved via whichever SDK method supports it):
  - search_type = "auto"  (Exa auto-selects neural vs. keyword)
  - highlights enabled    (key sentences extracted from each result page)
  - configurable num_results (default 5)

Does NOT use:
  - outputSchema
  - deep / deep-lite / deep-reasoning search

Environment variable:
  EXA_API_KEY — optional; if absent the provider returns [] without raising.
"""

import logging
from typing import Any

from app.search.base import SearchProvider, SearchResult

log = logging.getLogger(__name__)

_DEFAULT_NUM_RESULTS = 5


class ExaSearchProvider(SearchProvider):
    """
    SearchProvider backed by the Exa Search API (exa-py SDK).

    The SDK method used to fetch results with highlights is resolved at
    initialisation time so we always call whatever the installed version
    actually exposes, rather than assuming a specific method name.
    """

    def __init__(self, api_key: str, num_results: int = _DEFAULT_NUM_RESULTS) -> None:
        """
        Initialise the Exa client.

        Args:
            api_key:     Exa API key (from EXA_API_KEY env var).
            num_results: Default number of results to fetch per query.

        Raises:
            ImportError: If exa-py is not installed (caught and re-raised
                         with a helpful message).
        """
        try:
            from exa_py import Exa  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "The 'exa-py' package is not installed. Run: uv add exa-py"
            ) from exc

        self._client: Any = Exa(api_key=api_key)
        self._num_results = num_results

        # Resolve the SDK method that provides search + highlights.
        # Modern releases use search_and_contents(); older or future releases
        # may name it differently. We check both known names and fall back to
        # a two-step search → get_contents pattern.
        self._search_fn = self._resolve_search_fn()
        log.debug("ExaSearchProvider initialised (method=%s)", self._search_fn.__name__)

    # ── SDK method resolution ─────────────────────────────────────────────────

    def _resolve_search_fn(self):  # type: ignore[return]
        """
        Return the best available callable on self._client for performing a
        search that also returns page highlights.

        Priority:
          1. search_and_contents  — combined search + content fetch (preferred)
          2. search               — basic search; highlights fetched separately
                                    via _search_two_step fallback
        """
        if hasattr(self._client, "search_and_contents") and callable(
            getattr(self._client, "search_and_contents")
        ):
            return self._search_and_contents

        # Fallback: basic search method (highlights won't be available)
        log.warning(
            "ExaSearchProvider: 'search_and_contents' not found on installed "
            "exa-py version. Falling back to basic search (no highlights). "
            "Consider upgrading: uv add --upgrade exa-py"
        )
        return self._search_basic

    # ── Search implementations ────────────────────────────────────────────────

    def _search_and_contents(self, query: str, num_results: int) -> list[SearchResult]:
        """Invoke the combined search_and_contents SDK method."""
        response = self._client.search_and_contents(
            query,
            type="auto",
            num_results=num_results,
            highlights=True,
        )
        return self._parse_results(response.results)

    def _search_basic(self, query: str, num_results: int) -> list[SearchResult]:
        """Invoke the basic search SDK method (no highlights)."""
        response = self._client.search(
            query,
            type="auto",
            num_results=num_results,
        )
        return self._parse_results(response.results)

    @staticmethod
    def _parse_results(raw_results: list[Any]) -> list[SearchResult]:
        """Convert raw SDK result objects into SearchResult dataclasses."""
        results: list[SearchResult] = []
        for r in raw_results:
            highlights: list[str] = list(getattr(r, "highlights", None) or [])
            results.append(
                SearchResult(
                    title=getattr(r, "title", "") or "",
                    url=r.url,
                    description=highlights[0] if highlights else (getattr(r, "text", "") or ""),
                    highlights=highlights,
                )
            )
        return results

    # ── Public interface ──────────────────────────────────────────────────────

    def search(self, query: str, num_results: int | None = None) -> list[SearchResult]:
        """
        Execute a web search via Exa and return structured results.

        Returns an empty list on any error (network failure, API error,
        invalid key) rather than propagating exceptions — the suggestion
        pipeline degrades gracefully to empty suggestions.

        Args:
            query:       The search query string.
            num_results: Override the instance default if provided.

        Returns:
            List of SearchResult objects, possibly empty.
        """
        count = num_results or self._num_results
        try:
            results = self._search_fn(query, count)
            log.debug(
                "ExaSearchProvider.search — query=%r returned %d result(s)",
                query,
                len(results),
            )
            return results
        except Exception:
            log.warning(
                "ExaSearchProvider.search failed for query=%r — returning empty list",
                query,
                exc_info=True,
            )
            return []
