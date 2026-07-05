"""
app/models/__init__.py — Public API for the models package.

Import everything from here:
    from app.models import Source, Article, DailyDigest, Base
"""

from app.models.base import Base
from app.models.source import Source, SourceType
from app.models.article import Article, ProcessingStatus
from app.models.digest import DailyDigest

__all__ = [
    "Base",
    "Source",
    "SourceType",
    "Article",
    "ProcessingStatus",
    "DailyDigest",
]
