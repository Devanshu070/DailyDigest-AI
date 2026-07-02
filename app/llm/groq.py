"""
groq.py — Groq provider implementation.

Groq's SDK is OpenAI-compatible, making it a drop-in replacement.
Defaults to meta-llama/llama-4-scout-17b-16e-instruct — Groq's current
production-ready model, running at high speed on free tier.

Reads GROQ_API_KEY and GROQ_MODEL from the environment.
"""

import logging
import os

from app.llm.base import BaseLLMProvider, LLMError

log = logging.getLogger(__name__)

_DEFAULT_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
_MAX_TOKENS = 2048


class GroqProvider(BaseLLMProvider):
    """
    LLM provider backed by the Groq API.

    Defaults to meta-llama/llama-4-scout-17b-16e-instruct — Groq's current
    production-ready model. Override with the GROQ_MODEL env var.

    Environment variables:
        GROQ_API_KEY  — required (free at console.groq.com)
        GROQ_MODEL    — optional, defaults to meta-llama/llama-4-scout-17b-16e-instruct
    """

    def __init__(self):
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise LLMError(
                "GROQ_API_KEY is not set in the environment. "
            )
        self.model = os.environ.get("GROQ_MODEL", _DEFAULT_MODEL)

        try:
            from groq import Groq, APIError
            self._client = Groq(api_key=api_key)
            self._APIError = APIError
        except ImportError:
            raise LLMError(
                "The 'groq' package is not installed. Run: uv add groq"
            )
        log.debug("GroqProvider initialised with model=%s", self.model)


    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """
        Calls the Groq Chat Completions API with the given prompts.

        Returns:
            The model's reply as a plain string.

        Raises:
            LLMError: On API failure, rate-limit, or empty response.
        """
        log.debug(
            "GroqProvider.complete — model=%s, system=%d chars, user=%d chars",
            self.model,
            len(system_prompt),
            len(user_prompt),
        )

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                max_tokens=_MAX_TOKENS,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except self._APIError as exc:
            raise LLMError(f"Groq API error: {exc}") from exc

        choices = response.choices
        if not choices:
            raise LLMError("Groq returned an empty response (no choices).")

        text = choices[0].message.content
        if not text or not text.strip():
            raise LLMError("Groq returned an empty text response.")

        text = text.strip()
        log.debug(
            "GroqProvider.complete — received %d chars (finish_reason=%s)",
            len(text),
            choices[0].finish_reason,
        )
        return text
