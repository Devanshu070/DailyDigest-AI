"""
app/search/base.py — Abstract base class and data types for search providers.

The SearchProvider ABC defines the contract that all search provider
implementations must satisfy. The SearchResult dataclass is the common
currency passed between the search layer and the recommendation layer.

Keeping this abstraction means the rest of the pipeline never imports
provider-specific SDK types.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class SearchResult:
    """
    A single search result returned by a SearchProvider.

    Attributes:
        title:       Page or channel title.
        url:         Canonical URL of the result.
        description: Short description or first highlight snippet (may be empty).
        highlights:  List of key sentences extracted from the page by the provider.
                     Empty list when the provider does not support highlights.
    """

    title: str
    url: str
    description: str
    highlights: list[str] = field(default_factory=list)


class SearchProvider(ABC):
    """
    Minimal interface for web search providers.

    Implementors wrap a specific search SDK (Exa, etc.) inside search()
    and return plain SearchResult objects. All provider-specific logic
    stays inside the concrete subclass.
    """

    @abstractmethod
    def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        """
        Execute a web search and return results.

        Args:
            query:       The search query string.
            num_results: Maximum number of results to return.

        Returns:
            A list of SearchResult objects. Returns an empty list on failure
            rather than raising — callers should handle empty gracefully.
        """
        ...
