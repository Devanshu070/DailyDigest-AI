from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, TypedDict


class ArticleData(TypedDict):
    title: str
    url: str
    raw_content: str          # Full text — transcript or description fallback
    raw_content_source: str   # "transcript" | "description"
    published_at: datetime
    scraped_at: datetime


class BaseIngester(ABC):
    """
    Abstract base class for all content ingesters.

    Subclasses must implement:
      - fetch(source_url)  — retrieve raw feed/content from a source
      - parse(raw_data)    — convert raw data into a list of ArticleData dicts
    """

    @abstractmethod
    def fetch(self, source_url: str) -> Any:
        """
        Fetches the raw content or feed from the specified source URL.
        Returns whatever raw structure the source provides (e.g. feed entries).
        """
        ...

    @abstractmethod
    def parse(self, raw_data: Any) -> list[ArticleData]:
        """
        Parses the raw data returned by fetch() into structured ArticleData dicts.
        Each dict contains: title, url, raw_content, raw_content_source,
        published_at, and scraped_at.
        """
        ...
