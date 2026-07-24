"""
tests/test_source_suggestions.py — Unit tests for the source suggestions pipeline.

Covers:
  - duplicate URL removal
  - invalid URLs
  - already subscribed URLs
  - unsupported source types
  - malformed LLM output
  - Exa search failures
  - empty interests
  - cache hit & refresh bypass
"""

import uuid
from datetime import datetime, timezone
from typing import Any

import pytest

from app.llm.base import BaseLLMProvider, LLMError
from app.models.source import SourceType
from app.recommendations.service import RecommendationService, SubscribedSource
from app.schemas import SourceSuggestion
from app.search.base import SearchProvider, SearchResult
from app.suggestions.service import SuggestionService
from app.utils.suggestion_validation import SuggestionValidator
from app.utils.url_validation import deduplicate_by_url, is_valid_url, normalize_url


# ── Mock Objects ───────────────────────────────────────────────────────────────

class MockLLMProvider(BaseLLMProvider):
    """Configurable mock LLM provider for testing."""

    def __init__(
        self,
        query_response: str | None = None,
        recommendation_response: str | None = None,
        should_fail: bool = False,
    ) -> None:
        self.model = "mock-model"
        self.query_response = query_response or '{"queries": ["AI blogs", "Tech news"]}'
        self.recommendation_response = (
            recommendation_response
            or '{"recommendations": [{"name": "AI Blog", "url": "https://example.com/feed", "source_type": "blog", "recommendation_reason": "Matches AI interest"}]}'
        )
        self.should_fail = should_fail
        self.call_count = 0

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.call_count += 1
        if self.should_fail:
            raise LLMError("Mock LLM error")
        if "query specialist" in system_prompt.lower():
            return self.query_response
        return self.recommendation_response


class MockSearchProvider(SearchProvider):
    """Configurable mock SearchProvider for testing."""

    def __init__(self, results: list[SearchResult] | None = None, should_fail: bool = False) -> None:
        self.results = results if results is not None else [
            SearchResult(
                title="Example Blog",
                url="https://example.com/feed",
                description="An example blog",
                highlights=["Great AI posts"],
            )
        ]
        self.should_fail = should_fail
        self.call_count = 0

    def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        self.call_count += 1
        if self.should_fail:
            return []
        return self.results


# ── Validator Tests ────────────────────────────────────────────────────────────

def test_duplicate_url_removed() -> None:
    validator = SuggestionValidator()
    suggestions = [
        SourceSuggestion(
            name="Blog 1",
            url="https://example.com/feed/",
            source_type=SourceType.blog,
            recommendation_reason="Reason 1",
        ),
        SourceSuggestion(
            name="Blog 1 Duplicate",
            url="http://www.example.com/feed",
            source_type=SourceType.blog,
            recommendation_reason="Reason 2",
        ),
    ]
    validated = validator.validate(suggestions, subscriptions=[])
    assert len(validated) == 1
    assert validated[0].url == "https://example.com/feed"


def test_invalid_url_rejected() -> None:
    validator = SuggestionValidator()
    suggestions = [
        SourceSuggestion(
            name="Invalid URL",
            url="not-a-valid-url",
            source_type=SourceType.blog,
            recommendation_reason="Reason",
        ),
        SourceSuggestion(
            name="Valid URL",
            url="https://valid.com/rss",
            source_type=SourceType.blog,
            recommendation_reason="Reason",
        ),
    ]
    validated = validator.validate(suggestions, subscriptions=[])
    assert len(validated) == 1
    assert validated[0].url == "https://valid.com/rss"


def test_already_subscribed_removed() -> None:
    validator = SuggestionValidator()
    subscriptions = [
        SubscribedSource(name="Existing", url="https://existing.com/feed")
    ]
    suggestions = [
        SourceSuggestion(
            name="Existing",
            url="https://www.existing.com/feed/",  # Should normalize to match subscription
            source_type=SourceType.blog,
            recommendation_reason="Reason",
        ),
        SourceSuggestion(
            name="New Source",
            url="https://newsource.com/rss",
            source_type=SourceType.blog,
            recommendation_reason="Reason",
        ),
    ]
    validated = validator.validate(suggestions, subscriptions=subscriptions)
    assert len(validated) == 1
    assert validated[0].url == "https://newsource.com/rss"


def test_unsupported_type_rejected() -> None:
    validator = SuggestionValidator()
    suggestions = [
        SourceSuggestion(
            name="Podcast",
            url="https://podcast.com/rss",
            source_type="podcast",  # Unsupported type
            recommendation_reason="Reason",
        ),
        SourceSuggestion(
            name="YouTube Channel",
            url="https://youtube.com/@channel",
            source_type=SourceType.youtube,
            recommendation_reason="Reason",
        ),
    ]
    validated = validator.validate(suggestions, subscriptions=[])
    assert len(validated) == 1
    assert validated[0].source_type == SourceType.youtube


# ── RecommendationService Tests ───────────────────────────────────────────────

def test_malformed_llm_output() -> None:
    # Malformed non-JSON response from LLM
    mock_llm = MockLLMProvider(recommendation_response="Here are some recommendations: [not json]")
    service = RecommendationService(llm=mock_llm)

    candidates = [SearchResult(title="Blog", url="https://example.com", description="Desc")]
    results = service.rank_and_filter(
        interests_md="AI", candidates=candidates, subscriptions=[]
    )
    assert results == []


# ── SuggestionService Tests ────────────────────────────────────────────────────

def test_exa_failure_returns_empty() -> None:
    mock_search = MockSearchProvider(should_fail=True)
    mock_llm = MockLLMProvider()
    validator = SuggestionValidator()
    rec_service = RecommendationService(llm=mock_llm)

    service = SuggestionService(
        search_provider=mock_search,
        recommendation_service=rec_service,
        validator=validator,
        llm=mock_llm,
    )

    response = service.suggest(
        user_id=uuid.uuid4(),
        interests_md="AI and ML",
        subscriptions=[],
    )

    assert response.suggestions == []
    assert response.cached is False


def test_empty_interests_returns_empty() -> None:
    mock_search = MockSearchProvider()
    mock_llm = MockLLMProvider()
    validator = SuggestionValidator()
    rec_service = RecommendationService(llm=mock_llm)

    service = SuggestionService(
        search_provider=mock_search,
        recommendation_service=rec_service,
        validator=validator,
        llm=mock_llm,
    )

    response = service.suggest(
        user_id=uuid.uuid4(),
        interests_md="   ",
        subscriptions=[],
    )

    assert response.suggestions == []
    assert mock_search.call_count == 0


def test_cache_hit() -> None:
    mock_search = MockSearchProvider()
    mock_llm = MockLLMProvider()
    validator = SuggestionValidator()
    rec_service = RecommendationService(llm=mock_llm)

    service = SuggestionService(
        search_provider=mock_search,
        recommendation_service=rec_service,
        validator=validator,
        llm=mock_llm,
    )

    user_id = uuid.uuid4()
    interests = "Artificial Intelligence"

    # First call: cache miss, runs pipeline
    res1 = service.suggest(user_id=user_id, interests_md=interests, subscriptions=[])
    assert res1.cached is False
    assert len(res1.suggestions) == 1
    initial_call_count = mock_search.call_count

    # Second call: cache hit
    res2 = service.suggest(user_id=user_id, interests_md=interests, subscriptions=[])
    assert res2.cached is True
    assert res2.suggestions == res1.suggestions
    assert mock_search.call_count == initial_call_count


def test_refresh_bypasses_cache() -> None:
    mock_search = MockSearchProvider()
    mock_llm = MockLLMProvider()
    validator = SuggestionValidator()
    rec_service = RecommendationService(llm=mock_llm)

    service = SuggestionService(
        search_provider=mock_search,
        recommendation_service=rec_service,
        validator=validator,
        llm=mock_llm,
    )

    user_id = uuid.uuid4()
    interests = "Artificial Intelligence"

    # First call
    res1 = service.suggest(user_id=user_id, interests_md=interests, subscriptions=[])
    assert res1.cached is False

    # Second call with refresh=True
    res2 = service.suggest(user_id=user_id, interests_md=interests, subscriptions=[], refresh=True)
    assert res2.cached is False
    assert mock_search.call_count > 1
