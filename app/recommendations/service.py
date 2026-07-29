"""
app/recommendations/service.py — LLM-based source recommendation service.

RecommendationService is a pure LLM layer:
  - Accepts user interests, Exa candidate sources (with highlights), and
    the user's existing subscriptions.
  - Asks the LLM to rank and filter the candidates.
  - Returns a list of SourceSuggestion objects.

This service never calls Exa or any other search provider. All search
results arrive as pre-built SearchResult dataclasses from the orchestrator
(SuggestionService).

The LLM is used only to:
  1. Make relevance judgements using interests + candidate info + highlights.
  2. Produce a recommendation reason for each selected source.

It does NOT make up sources — it only evaluates candidates passed to it.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from app.llm.base import BaseLLMProvider, LLMError
from app.schemas import SourceSuggestion
from app.search.base import SearchResult

log = logging.getLogger(__name__)


@dataclass
class SubscribedSource:
    """Lightweight representation of a source the user already follows."""

    name: str     # display name stored in user_source_aliases
    url: str      # already-normalised URL from the sources table


# ── Prompts ────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a content curator. Your job is to evaluate a list of candidate websites
and YouTube channels and decide which ones are worth recommending to a user
based on their stated interests.

Rules you MUST follow:
1. Only recommend sources from the provided candidate list — never invent URLs.
2. Prefer sources with strong evidence of relevance (use the provided highlight
   snippets as evidence about what the page covers).
3. Skip article pages, individual blog posts, aggregator directories, and
   low-quality or generic sites.
4. Avoid recommending sources the user is already subscribed to.
5. Return between 0 and 10 recommendations. It is fine to return fewer if
   quality candidates are scarce.
6. For each recommendation, write a concise reason (1–2 sentences) explaining
   why it matches the user's interests. Be specific — reference the interests
   and the evidence from highlights.
7. Classify each source as either "blog" or "youtube". YouTube channels must
   have a youtube.com URL.
8. Return ONLY a JSON object matching this schema — no prose, no markdown:

{
  "recommendations": [
    {
      "name": "<source name>",
      "url": "<exact URL from candidate list>",
      "source_type": "blog" | "youtube",
      "recommendation_reason": "<1-2 sentence reason>"
    }
  ]
}
"""

_FALLBACK_SYSTEM_PROMPT = """\
You are an expert tech content curator. Given a user's stated interests, recommend
high-quality RSS blogs, engineering newsletters, and YouTube channels.

Rules you MUST follow:
1. Suggest real, well-known tech blogs, company engineering blogs, tech newsletters, or YouTube channels.
2. For each source, provide its real canonical website or YouTube channel URL.
3. Classify each source as either "blog" or "youtube". YouTube channels must have a youtube.com URL.
4. Avoid recommending sources the user is already subscribed to.
5. Return between 3 and 8 top recommendations.
6. For each recommendation, write a concise reason (1–2 sentences) explaining why it matches the user's interests.
7. Return ONLY a JSON object matching this schema — no prose, no markdown:

{
  "recommendations": [
    {
      "name": "<source name>",
      "url": "<canonical URL>",
      "source_type": "blog" | "youtube",
      "recommendation_reason": "<1–2 sentence reason>"
    }
  ]
}
"""


def _build_fallback_user_prompt(
    interests_md: str,
    subscriptions: list["SubscribedSource"],
) -> str:
    if subscriptions:
        sub_lines = [f"- {s.name} ({s.url})" for s in subscriptions]
        subscriptions_block = "\n".join(sub_lines)
    else:
        subscriptions_block = "(none)"

    return f"""\
## User Interests

{interests_md.strip()}

## Already Subscribed (avoid recommending these)

{subscriptions_block}

Recommend top relevant RSS blogs and YouTube channels matching the user's interests as JSON.
"""


def _build_user_prompt(
    interests_md: str,
    candidates: list[SearchResult],
    subscriptions: list[SubscribedSource],
) -> str:
    """Construct the user-turn prompt from interests, candidates, and subscriptions."""

    # Format candidates
    candidate_lines: list[str] = []
    for i, c in enumerate(candidates, start=1):
        lines = [f"{i}. [{c.title}]({c.url})"]
        if c.description:
            lines.append(f"   Description: {c.description}")
        if c.highlights:
            snippet = " | ".join(h.strip() for h in c.highlights[:3])
            lines.append(f"   Highlights: {snippet}")
        candidate_lines.append("\n".join(lines))

    candidates_block = "\n\n".join(candidate_lines) or "(no candidates)"

    # Format existing subscriptions
    if subscriptions:
        sub_lines = [f"- {s.name} ({s.url})" for s in subscriptions]
        subscriptions_block = "\n".join(sub_lines)
    else:
        subscriptions_block = "(none)"

    return f"""\
## User Interests

{interests_md.strip()}

## Candidate Sources

{candidates_block}

## Already Subscribed (avoid recommending these)

{subscriptions_block}

Evaluate the candidate sources and return your recommendations as JSON.
"""


# ── Service ────────────────────────────────────────────────────────────────────

class RecommendationService:
    """
    Rank and filter candidate search results using an LLM.

    This service is stateless — it does not cache, persist, or call any
    external APIs other than the configured LLM provider.
    """

    def __init__(self, llm: BaseLLMProvider) -> None:
        self._llm = llm

    def rank_and_filter(
        self,
        interests_md: str,
        candidates: list[SearchResult],
        subscriptions: list[SubscribedSource],
    ) -> list[SourceSuggestion]:
        """
        Ask the LLM to select and rank the most relevant candidate sources.

        Args:
            interests_md:  The user's interest profile in Markdown.
            candidates:    Candidate sources from ExaSearchProvider, including
                           highlight snippets for evidence.
            subscriptions: Sources the user already follows (used as a hint
                           — authoritative deduplication happens in the
                           validator, not here).

        Returns:
            A list of SourceSuggestion objects. Returns [] on LLM failure
            rather than propagating the exception.
        """
        if not interests_md.strip():
            log.debug("RecommendationService: empty interests — skipping LLM call")
            return []

        if not candidates:
            log.info("RecommendationService: no search candidates — using direct LLM recommendation")
            system_prompt = _FALLBACK_SYSTEM_PROMPT
            user_prompt = _build_fallback_user_prompt(interests_md, subscriptions)
        else:
            system_prompt = _SYSTEM_PROMPT
            user_prompt = _build_user_prompt(interests_md, candidates, subscriptions)

        try:
            raw = self._llm.complete(system_prompt, user_prompt)
        except LLMError:
            log.warning("RecommendationService: LLM call failed", exc_info=True)
            return []

        return self._parse_response(raw)

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _parse_response(raw: str) -> list[SourceSuggestion]:
        """
        Extract the JSON payload from the LLM response and convert it into
        SourceSuggestion objects. Returns [] on any parse failure.
        """
        # Strip optional markdown fences the LLM might wrap around the JSON
        cleaned = raw.strip()
        fence_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", cleaned)
        if fence_match:
            cleaned = fence_match.group(1).strip()
        else:
            json_match = re.search(r"\{[\s\S]*\}", cleaned)
            if json_match:
                cleaned = json_match.group(0).strip()

        try:
            data: Any = json.loads(cleaned)
        except json.JSONDecodeError:
            log.warning(
                "RecommendationService: LLM returned non-JSON output — skipping.\n%s",
                raw[:500],
            )
            return []

        if not isinstance(data, dict) or "recommendations" not in data:
            log.warning(
                "RecommendationService: unexpected JSON shape — skipping.\n%s", data
            )
            return []

        suggestions: list[SourceSuggestion] = []
        for item in data.get("recommendations", []):
            try:
                suggestions.append(
                    SourceSuggestion(
                        name=str(item["name"]),
                        url=str(item["url"]),
                        source_type=str(item["source_type"]),
                        recommendation_reason=str(item["recommendation_reason"]),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                log.debug("RecommendationService: skipping malformed item %s — %s", item, exc)

        log.debug("RecommendationService: parsed %d recommendation(s)", len(suggestions))
        return suggestions
