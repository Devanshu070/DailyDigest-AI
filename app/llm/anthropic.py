"""
anthropic.py — Anthropic (Claude) provider implementation.

Reads ANTHROPIC_API_KEY and ANTHROPIC_MODEL from the environment.
Defaults to claude-sonnet-4-5 if ANTHROPIC_MODEL is not set.
"""

import logging
import os

import anthropic

from app.llm.base import BaseLLMProvider, LLMError

log = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-sonnet-4-5"
_MAX_TOKENS = 2048


class AnthropicProvider(BaseLLMProvider):
    """
    LLM provider backed by the Anthropic Messages API (Claude models).

    Environment variables:
        ANTHROPIC_API_KEY  — required
        ANTHROPIC_MODEL    — optional, defaults to claude-sonnet-4-5
    """

    def __init__(self):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMError(
                "ANTHROPIC_API_KEY is not set in the environment. "
                "Add it to your .env file."
            )
        self.model = os.environ.get("ANTHROPIC_MODEL", _DEFAULT_MODEL)
        self._client = anthropic.Anthropic(api_key=api_key)
        log.debug("AnthropicProvider initialised with model=%s", self.model)

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """
        Calls the Anthropic Messages API with the given prompts.

        Returns:
            The model's reply as a plain string.

        Raises:
            LLMError: On API failure, rate-limit, or empty response.
        """
        log.debug(
            "AnthropicProvider.complete — model=%s, system=%d chars, user=%d chars",
            self.model,
            len(system_prompt),
            len(user_prompt),
        )

        try:
            message = self._client.messages.create(
                model=self.model,
                max_tokens=_MAX_TOKENS,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except anthropic.APIError as exc:
            raise LLMError(f"Anthropic API error: {exc}") from exc

        # Extract text from the first content block
        if not message.content:
            raise LLMError("Anthropic returned an empty response (no content blocks).")

        text = message.content[0].text.strip()
        if not text:
            raise LLMError("Anthropic returned an empty text response.")

        log.debug(
            "AnthropicProvider.complete — received %d chars (stop_reason=%s)",
            len(text),
            message.stop_reason,
        )
        return text
