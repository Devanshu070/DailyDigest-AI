"""
generator.py — Public facade for the digest pipeline.

Ties together the two steps:
  Step 1 (summarizer.py): per-article summarization
  Step 2 (assembler.py):  digest assembly from all summaries

Import from here — do not import summarizer or assembler directly.
"""

from app.digest.models import ArticleSummaryInput, DigestResult
from app.digest.summarizer import summarize_article, HIERARCHICAL_THRESHOLD
from app.digest.assembler import generate_digest, markdown_to_html, PROMPT_VERSION

__all__ = [
    "ArticleSummaryInput",
    "DigestResult",
    "summarize_article",
    "generate_digest",
    "markdown_to_html",
    "HIERARCHICAL_THRESHOLD",
    "PROMPT_VERSION",
]
