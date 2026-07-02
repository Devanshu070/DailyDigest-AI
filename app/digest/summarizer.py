"""
summarizer.py — Step 1: Per-article LLM summarization.

Two strategies, selected by token_count:
  - Standard:      Single-pass LLM call for normal-length articles.
  - Hierarchical:  Context-preserving chunked summarization for large
                   transcripts (e.g. long YouTube videos).
"""

import logging

from app.llm.base import BaseLLMProvider
from app.digest.models import ArticleSummaryInput

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Routing threshold
# ---------------------------------------------------------------------------

# Articles above this estimated token count use hierarchical summarization.
# ~6000 tokens ≈ a 45-60 minute YouTube transcript.
HIERARCHICAL_THRESHOLD = 6_000

# Chunk size and overlap for hierarchical summarization (in characters).
# 12_000 chars ≈ ~3000 tokens — safely fits any model's context window while
# leaving room for the accumulated context carried over from prior chunks.
_CHUNK_SIZE = 12_000
_CHUNK_OVERLAP = 800

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_STANDARD_SYSTEM = (
    "You are a precise, no-filler summarizer. "
    "Extract the core insight from an article or transcript. "
    "Write as much as the content genuinely deserves — 2-3 sentences if brief, "
    "more if there is real substance. "
    "Never pad. Maximum 500 words. Plain text only."
)

_CHUNK_SYSTEM = (
    "You are summarizing a section of a long article or transcript. "
    "You will be provided with summaries of previous sections for context, "
    "followed by the new section to summarize. "
    "Your task is to summarize ONLY the new section, using the previous "
    "summaries strictly to understand the ongoing context (e.g., resolving pronouns). "
    "Do not restate the previous summaries. "
    "Output a concise but detailed summary of the new section. "
    "Never pad. Maximum 500 words."
)

_SYNTHESIS_SYSTEM = (
    "You are synthesizing a final summary from a series of sequential section "
    "summaries of a long article or transcript. Integrate all key ideas and "
    "preserve the narrative arc. Produce a single flowing summary as if written "
    "from the full content. Never pad. Maximum 500 words. Plain text only."
)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def summarize_article(article: ArticleSummaryInput, llm: BaseLLMProvider) -> str:
    """
    Summarizes a single article using the appropriate strategy.

    Routes to standard or hierarchical summarization based on token_count.
    Returns a plain-text summary string (max ~300 words).
    """
    if article.token_count <= HIERARCHICAL_THRESHOLD:
        return _standard_summarize(article, llm)
    log.info(
        "Article '%s' has %d tokens — using hierarchical summarization.",
        article.title, article.token_count,
    )
    return _hierarchical_summarize(article, llm)


# ---------------------------------------------------------------------------
# Internal strategies
# ---------------------------------------------------------------------------

def _standard_summarize(article: ArticleSummaryInput, llm: BaseLLMProvider) -> str:
    """Single-pass summarization for normal-length articles."""
    log.debug("Standard summarization for '%s' (%d tokens)", article.title, article.token_count)
    user_prompt = f"Article title: {article.title}\n\nContent:\n{article.cleaned_content}"
    return llm.complete(_STANDARD_SYSTEM, user_prompt)


def _hierarchical_summarize(article: ArticleSummaryInput, llm: BaseLLMProvider) -> str:
    """
    Context-preserving hierarchical summarization for large transcripts.

    Processes overlapping chunks progressively so later chunks receive the
    running summary of earlier sections — preserving narrative continuity
    across the full length of the content.

    A final synthesis pass produces one coherent article summary.
    """
    chunks = _split_into_chunks(article.cleaned_content, _CHUNK_SIZE, _CHUNK_OVERLAP)
    log.debug(
        "Hierarchical summarization for '%s': %d chunks", article.title, len(chunks)
    )

    chunk_summaries = []
    for i, chunk in enumerate(chunks):
        if i == 0:
            user_prompt = (
                f"Article title: {article.title}\n\n"
                f"First section:\n{chunk}"
            )
        else:
            previous_context = "\n".join(f"- Part {j+1}: {s}" for j, s in enumerate(chunk_summaries))
            user_prompt = (
                f"Article title: {article.title}\n\n"
                f"Summaries of previous sections for context:\n{previous_context}\n\n"
                f"New section to summarize:\n{chunk}"
            )
        
        current_summary = llm.complete(_CHUNK_SYSTEM, user_prompt)
        chunk_summaries.append(current_summary)
        log.debug("Chunk %d/%d done — summary: %d chars", i + 1, len(chunks), len(current_summary))

    # Synthesis pass
    all_summaries = "\n\n".join(f"--- Part {j+1} ---\n{s}" for j, s in enumerate(chunk_summaries))
    synthesis_prompt = (
        f"Article title: {article.title}\n\n"
        f"Sequential summaries of all parts:\n\n{all_summaries}"
    )
    final_summary = llm.complete(_SYNTHESIS_SYSTEM, synthesis_prompt)
    log.debug("Final synthesis for '%s': %d chars", article.title, len(final_summary))
    return final_summary


def _split_into_chunks(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Splits text into overlapping character-count chunks."""
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - overlap  # step back by overlap to preserve boundary context
    return chunks