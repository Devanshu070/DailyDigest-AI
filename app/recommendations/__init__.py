"""
app/recommendations/__init__.py — Public API for the recommendations package.

Usage:
    from app.recommendations import RecommendationService
"""

from app.recommendations.service import RecommendationService

__all__ = ["RecommendationService"]
