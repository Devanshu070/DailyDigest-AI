"""
app/search/__init__.py — Public API for the search package.

Usage:
    from app.search import SearchProvider, SearchResult, ExaSearchProvider
"""

from app.search.base import SearchProvider, SearchResult
from app.search.exa import ExaSearchProvider

__all__ = ["SearchProvider", "SearchResult", "ExaSearchProvider"]
