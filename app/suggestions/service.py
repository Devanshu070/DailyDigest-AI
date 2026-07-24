"""
app/suggestions/service.py — SuggestionService orchestrator.

SuggestionService coordinates the full source-suggestion pipeline:

  1. Cache check         — return immediately if a valid cached result exists
  2. Query generation    — ask the LLM to generate 3–5 Exa search queries
  3. Exa search          — run each query (5 results each, with highlights)
  4. Candidate dedup     — merge results, cap at MAX_CANDIDATES before LLM
  5. LLM ranking         — RecommendationService selects + scores candidates
  6. Validation          — SuggestionValidator applies deterministic checks
  7. Cache store         — persist the result with a timestamp
  8. Return              — SourceSuggestionsResponse

Caching:
  - In-memory dict keyed by user UUID.
  - TTL: CACHE_TTL_SECONDS (24 hours by default).
  - `refresh=True` bypasses the cache read and overwrites after regenerating.
  - Cache resets on server restart (acceptable for V1; swap for Redis later).
"""

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.llm import llm_assembler
from app.llm.base import BaseLLMProvider, LLMError
from app.recommendations.service import RecommendationService, SubscribedSource
from app.schemas import SourceSuggestion, SourceSuggestionsResponse
from app.search.base import SearchProvider, SearchResult
from app.utils.suggestion_validation import SuggestionValidator
from app.utils.url_validation import deduplicate_by_url

log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

CACHE_TTL_SECONDS: int = 86_400        # 24 hours
MAX_QUERIES: int = 5                    # LLM generates at most this many queries
RESULTS_PER_QUERY: int = 5             # Exa results per query
MAX_CANDIDATES: int = 25               # hard cap before LLM ranking call

# ── Prompt for query generation ────────────────────────────────────────────────

_QUERY_GEN_SYSTEM = """\
You are a search query specialist. Given a user's interest profile, generate
precise search queries that will help find high-quality RSS blogs and YouTube
channels covering those interests.

Rules:
- Generate between 3 and 5 queries.
- Each query should target a distinct sub-topic or content format.
- Write queries that are likely to surface newsletter homepages, blog indexes,
  and YouTube channel pages — not individual articles or videos.
- Return ONLY a JSON object:

{"queries": ["query 1", "query 2", ...]}
"""

_QUERY_GEN_USER_TEMPLATE = """\
## User Interests

{interests_md}

Generate search queries to find relevant RSS blogs and YouTube channels.
"""

# ── Cache ──────────────────────────────────────────────────────────────────────

@dataclass
class _CachedResult:
    response: SourceSuggestionsResponse
    generated_at: datetime


# ── Service ────────────────────────────────────────────────────────────────────

class SuggestionService:
    """
    Orchestrator for the source suggestion pipeline.

    Instantiate once and reuse (module-level singleton injected via FastAPI
    Depends). The in-memory cache is stored on the instance.
    """

    def __init__(
        self,
        search_provider: SearchProvider,
        recommendation_service: RecommendationService,
        validator: SuggestionValidator,
        llm: BaseLLMProvider | None = None,
    ) -> None:
        self._search = search_provider
        self._recommender = recommendation_service
        self._validator = validator
        self._llm: BaseLLMProvider = llm or llm_assembler
        self._cache: dict[uuid.UUID, _CachedResult] = {}

    # ── Public API ─────────────────────────────────────────────────────────────

    def suggest(
        self,
        user_id: uuid.UUID,
        interests_md: str,
        subscriptions: list[SubscribedSource],
        refresh: bool = False,
    ) -> SourceSuggestionsResponse:
        """
        Run the full suggestion pipeline and return a response.

        Args:
            user_id:       UUID of the requesting user (cache key).
            interests_md:  User's interest profile in Markdown.
            subscriptions: User's current source subscriptions.
            refresh:       If True, bypass the cache and regenerate.

        Returns:
            SourceSuggestionsResponse with suggestions, cached flag, and timestamp.
        """
        # 1. Cache check
        if not refresh:
            cached = self._get_cached(user_id)
            if cached is not None:
                log.debug("SuggestionService: returning cached result for user %s", user_id)
                return cached

        # 2–7. Full pipeline
        suggestions = self._run_pipeline(interests_md, subscriptions)

        now = datetime.now(tz=timezone.utc)
        response = SourceSuggestionsResponse(
            suggestions=suggestions,
            cached=False,
            generated_at=now,
        )

        # 7. Store in cache
        self._cache[user_id] = _CachedResult(response=response, generated_at=now)
        log.debug(
            "SuggestionService: pipeline complete — %d suggestion(s) for user %s",
            len(suggestions),
            user_id,
        )
        return response

    # ── Cache helpers ──────────────────────────────────────────────────────────

    def _get_cached(self, user_id: uuid.UUID) -> SourceSuggestionsResponse | None:
        """Return cached response if still within TTL, else None."""
        entry = self._cache.get(user_id)
        if entry is None:
            return None
        age = datetime.now(tz=timezone.utc) - entry.generated_at
        if age > timedelta(seconds=CACHE_TTL_SECONDS):
            del self._cache[user_id]
            return None
        # Return a copy with cached=True so the caller knows the source
        return SourceSuggestionsResponse(
            suggestions=entry.response.suggestions,
            cached=True,
            generated_at=entry.generated_at,
        )

    # ── Pipeline steps ─────────────────────────────────────────────────────────

    def _run_pipeline(
        self,
        interests_md: str,
        subscriptions: list[SubscribedSource],
    ) -> list[SourceSuggestion]:
        """Execute steps 2–6 of the pipeline and return validated suggestions."""

        # 2. Generate search queries
        queries = self._generate_queries(interests_md)
        if not queries:
            log.info("SuggestionService: no queries generated — returning empty suggestions")
            return []

        # 3. Run Exa search
        raw_results: list[SearchResult] = []
        for query in queries:
            results = self._search.search(query, num_results=RESULTS_PER_QUERY)
            raw_results.extend(results)
            log.debug("SuggestionService: query=%r → %d result(s)", query, len(results))

        # 4. Dedup + cap candidates
        candidates = deduplicate_by_url(raw_results, key_fn=lambda r: r.url)
        if len(candidates) > MAX_CANDIDATES:
            candidates = candidates[:MAX_CANDIDATES]
        log.debug("SuggestionService: %d unique candidate(s) after dedup", len(candidates))

        if not candidates:
            return []

        # 5. LLM ranking
        llm_suggestions = self._recommender.rank_and_filter(
            interests_md=interests_md,
            candidates=candidates,
            subscriptions=subscriptions,
        )

        # 6. Deterministic validation
        validated = self._validator.validate(llm_suggestions, subscriptions)
        return validated

    def _generate_queries(self, interests_md: str) -> list[str]:
        """
        Use the LLM to generate 3–5 targeted Exa search queries from the
        user's interest profile. Returns [] on empty interests or LLM failure.
        """
        if not interests_md.strip():
            return []

        user_prompt = _QUERY_GEN_USER_TEMPLATE.format(interests_md=interests_md.strip())

        try:
            raw = self._llm.complete(_QUERY_GEN_SYSTEM, user_prompt)
        except LLMError:
            log.warning("SuggestionService: query generation LLM call failed", exc_info=True)
            return []

        queries = self._parse_queries(raw)
        log.debug("SuggestionService: generated %d search query/queries", len(queries))
        return queries[:MAX_QUERIES]

    @staticmethod
    def _parse_queries(raw: str) -> list[str]:
        """
        Extract the query list from the LLM's JSON response.
        Returns [] on parse failure.
        """
        cleaned = raw.strip()
        fence_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", cleaned)
        if fence_match:
            cleaned = fence_match.group(1).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            log.warning(
                "SuggestionService: query gen returned non-JSON — skipping.\n%s", raw[:300]
            )
            return []

        queries = data.get("queries", [])
        if not isinstance(queries, list):
            return []

        return [str(q).strip() for q in queries if str(q).strip()]
