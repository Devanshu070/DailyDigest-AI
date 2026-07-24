"""
app/utils/suggestion_validation.py — Deterministic post-LLM validation.

SuggestionValidator runs after RecommendationService and applies
authoritative, LLM-agnostic checks:

  1. Reject malformed URLs
  2. Reject unsupported source types
  3. Normalise URLs (via app.utils.url_validation.normalize_url)
  4. Deduplicate by normalised URL (keep first occurrence)
  5. Drop URLs already in the user's existing subscriptions

This validation is mandatory. The pipeline never relies solely on the
LLM for deduplication or subscription checking.
"""

import logging
from typing import TYPE_CHECKING

from app.models.source import SourceType
from app.schemas import SourceSuggestion
from app.utils.url_validation import is_valid_url, normalize_url

if TYPE_CHECKING:
    from app.recommendations.service import SubscribedSource

log = logging.getLogger(__name__)


class SuggestionValidator:
    """
    Stateless deterministic validator for LLM-produced suggestions.

    All methods are pure — no database access, no I/O.
    """

    def validate(
        self,
        suggestions: list[SourceSuggestion],
        subscriptions: "list[SubscribedSource]",
    ) -> list[SourceSuggestion]:
        """
        Apply all validation rules and return a cleaned list of suggestions.

        Checks applied in order:
          1. URL is syntactically valid
          2. source_type is a known SourceType value
          3. Deduplicate by normalised URL (first occurrence wins)
          4. URL is not already subscribed by the user

        Args:
            suggestions:   Raw suggestions from RecommendationService.
            subscriptions: User's current subscriptions (name + normalised URL).

        Returns:
            Validated, deduplicated list of SourceSuggestion objects.
        """
        subscribed_urls: set[str] = {normalize_url(s.url) for s in subscriptions}

        seen_urls: set[str] = set()
        valid: list[SourceSuggestion] = []

        for s in suggestions:
            canonical = normalize_url(s.url)

            # 1. URL validity
            if not is_valid_url(s.url):
                log.debug("Validator: dropped malformed URL %r", s.url)
                continue

            # 2. Supported source type
            if not self._is_supported_type(s.source_type):
                log.debug(
                    "Validator: dropped unsupported source_type %r for %r",
                    s.source_type,
                    s.url,
                )
                continue

            # 3. Deduplication
            if canonical in seen_urls:
                log.debug("Validator: dropped duplicate URL %r", s.url)
                continue

            # 4. Already subscribed
            if canonical in subscribed_urls:
                log.debug("Validator: dropped already-subscribed URL %r", s.url)
                continue

            seen_urls.add(canonical)
            # Store the suggestion with its normalised URL so downstream
            # consumers (the API response and the frontend add flow) always
            # receive a canonical URL.
            valid.append(
                SourceSuggestion(
                    name=s.name,
                    url=canonical,
                    source_type=s.source_type,
                    recommendation_reason=s.recommendation_reason,
                )
            )

        log.debug(
            "Validator: %d suggestion(s) in, %d passed validation",
            len(suggestions),
            len(valid),
        )
        return valid

    @staticmethod
    def _is_supported_type(source_type: str) -> bool:
        """Return True if source_type is a recognised SourceType enum value."""
        try:
            SourceType(source_type)
            return True
        except ValueError:
            return False
