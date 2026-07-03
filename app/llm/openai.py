"""
openai.py — OpenAI provider implementation.

Reads OPENAI_API_KEY and OPENAI_MODEL from the environment.
Defaults to gpt-4o-mini if OPENAI_MODEL is not set.
"""

import logging
import os

import openai as openai_sdk

from app.llm.base import BaseLLMProvider, LLMError

log = logging.getLogger(__name__)

_DEFAULT_MODEL = "gpt-4o-mini"
_MAX_TOKENS = 2048


class OpenAIProvider(BaseLLMProvider):
    """
    LLM provider backed by the OpenAI Chat Completions API.

    Environment variables:
        OPENAI_API_KEY  — required
        OPENAI_MODEL    — optional, defaults to gpt-4o-mini
    """

    def __init__(self):
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise LLMError(
                "OPENAI_API_KEY is not set in the environment. "
                "Add it to your .env file."
            )
        self.model = os.environ.get("OPENAI_MODEL", _DEFAULT_MODEL)
        self._client = openai_sdk.OpenAI(api_key=api_key)
        log.debug("OpenAIProvider initialised with model=%s", self.model)

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """
        Calls the OpenAI Chat Completions API with the given prompts.

        Returns:
            The model's reply as a plain string.

        Raises:
            LLMError: On API failure, rate-limit, or empty response.
        """
        log.debug(
            "OpenAIProvider.complete — model=%s, system=%d chars, user=%d chars",
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
        except openai_sdk.APIError as exc:
            raise LLMError(f"OpenAI API error: {exc}") from exc

        # Extract text from the first choice
        choices = response.choices
        if not choices:
            raise LLMError("OpenAI returned an empty response (no choices).")

        text = choices[0].message.content
        if not text or not text.strip():
            raise LLMError("OpenAI returned an empty text response.")

        text = text.strip()
        log.debug(
            "OpenAIProvider.complete — received %d chars (finish_reason=%s)",
            len(text),
            choices[0].finish_reason,
        )
        return text
