"""
models.py — Shared data classes for the digest pipeline.
"""

from dataclasses import dataclass


@dataclass
class ArticleSummaryInput:
    """Minimal article data the generator needs to produce a summary."""
    title: str
    url: str
    source_name: str          # e.g. "Lex Fridman (YouTube)", "Anthropic Blog"
    cleaned_content: str
    token_count: int


@dataclass
class DigestResult:
    """Returned by generate_digest()."""
    markdown_content: str
    html_content: str
    model_used: str
    prompt_version: str
    article_count: int        # number of articles included
