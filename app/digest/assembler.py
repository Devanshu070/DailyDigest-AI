"""
assembler.py — Step 2: Digest assembly from article summaries.

Takes all per-article summaries (from summarizer.py), reads the user's
interests (from DB or disk fallback), and produces a personalized Markdown
digest via a single LLM call. Converts the output to HTML.
"""

import logging
import textwrap
from pathlib import Path

import markdown as md_lib

from app.llm.base import BaseLLMProvider
from app.digest.models import ArticleSummaryInput, DigestResult

log = logging.getLogger(__name__)

PROMPT_VERSION = "v1.0"

_INTERESTS_PATH = Path(__file__).parent.parent / "prompts" / "user_interests.md"

# ---------------------------------------------------------------------------
# Digest system prompt
# ---------------------------------------------------------------------------

_DIGEST_SYSTEM_TEMPLATE = textwrap.dedent("""\
    You are a personal research assistant curating a daily digest.

    The user's interests and preferences:
    {user_interests}

    Rules for the digest:
    - Only include articles genuinely worth the user's attention.
    - Target up to 10 high-value articles. On quieter days, fewer is correct.
      Prioritize signal quality over filling a fixed length.
    - Do not pad. 3 great snippets beat 8 mediocre ones.
    - Each snippet must contain actual insight and specific details —
      not just a restatement of the headline.
    - Filter out articles that cover the exact same news or similar discussions.
      Merge their key insights into a single topic block while citing all relevant arcticles.
    - Format in Markdown. Use ## for the topic or article title, followed by
      the key insight in prose form.
    - For EVERY snippet (whether a single article or merged), put a "Sources:"
      line at the bottom with clickable markdown links (e.g., [Source Name](URL)).
    - Omit articles you consider low-signal or irrelevant.
""")

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_digest(
    articles: list[ArticleSummaryInput],
    summaries: list[str],
    llm: BaseLLMProvider,
    interests_md: str | None = None,
) -> DigestResult:
    """
    Assembles a personalized daily digest from article summaries.

    Args:
        articles:      List of ArticleSummaryInput (for title/source/url context).
        summaries:     Corresponding summaries from Step 1 (same order).
        llm:           The LLM provider to use.
        interests_md:  The user's interest profile as a markdown string.
                       If None, falls back to reading app/prompts/user_interests.md
                       from disk (backward-compatible for single-user setups).

    Returns:
        DigestResult containing markdown_content, html_content, model_used,
        prompt_version, and article_count.

    Raises:
        ValueError: If articles and summaries have different lengths.
        LLMError:   If the LLM call fails.
    """
    if len(articles) != len(summaries):
        raise ValueError(
            f"articles ({len(articles)}) and summaries ({len(summaries)}) "
            "must have the same length."
        )

    # Use the passed-in interests if provided; else fall back to the static file
    user_interests = interests_md.strip() if interests_md and interests_md.strip() \
        else _load_user_interests()

    system_prompt = _DIGEST_SYSTEM_TEMPLATE.format(
        user_interests=user_interests
    )
    user_prompt = _build_user_prompt(articles, summaries)

    log.info("Generating digest from %d summaries (prompt_version=%s)…", len(articles), PROMPT_VERSION)

    markdown_content = llm.complete(system_prompt, user_prompt)
    html_content = markdown_to_html(markdown_content)
    model_used = getattr(llm, "model", type(llm).__name__)

    log.info(
        "Digest generated: %d chars markdown, %d chars HTML (model=%s)",
        len(markdown_content), len(html_content), model_used,
    )

    return DigestResult(
        markdown_content=markdown_content,
        html_content=html_content,
        model_used=model_used,
        prompt_version=PROMPT_VERSION,
        article_count=len(articles),
    )


def markdown_to_html(markdown_text: str) -> str:
    """Converts a Markdown string to an HTML string."""
    return md_lib.markdown(markdown_text, extensions=["extra", "nl2br"])


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_user_interests() -> str:
    """Reads user_interests.md from disk, or returns a generic fallback."""
    if _INTERESTS_PATH.exists():
        content = _INTERESTS_PATH.read_text(encoding="utf-8").strip()
        if content:
            return content
    log.warning("user_interests.md not found at %s — using generic fallback.", _INTERESTS_PATH)
    return (
        "The user is interested in AI research, machine learning, technology trends, "
        "and software engineering. Prioritize technical depth and novel insights."
    )


def _build_user_prompt(articles: list[ArticleSummaryInput], summaries: list[str]) -> str:
    """Assembles the user-facing prompt block listing all article summaries."""
    lines = ["Here are today's article summaries:\n"]
    for i, (article, summary) in enumerate(zip(articles, summaries), start=1):
        lines.append(f"[Article {i}]")
        lines.append(f"  Title:   {article.title}")
        lines.append(f"  Source:  {article.source_name}")
        lines.append(f"  URL:     {article.url}")
        lines.append(f"  Summary: {summary}")
        lines.append("")
    return "\n".join(lines)