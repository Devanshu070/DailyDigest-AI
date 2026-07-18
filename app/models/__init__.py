"""
app/models/__init__.py — Public API for the models package.

Import everything from here:
    from app.models import Source, Article, User, UserSourceAlias, Base
"""

from app.models.base import Base
from app.models.source import Source, SourceType
from app.models.article import Article, ProcessingStatus
from app.models.digest import DailyDigest
from app.models.user import User
from app.models.user_source_alias import UserSourceAlias

__all__ = [
    "Base",
    "Source",
    "SourceType",
    "Article",
    "ProcessingStatus",
    "DailyDigest",
    "User",
    "UserSourceAlias",
]
