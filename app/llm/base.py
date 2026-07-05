"""
base.py — Abstract base class for all LLM providers.

The entire application (digest generator, summarizer) only ever imports
BaseLLMProvider and calls complete(). It never imports Anthropic or OpenAI
directly. Switching providers requires only a config change.
"""

from abc import ABC, abstractmethod


class BaseLLMProvider(ABC):
    """
    Minimal interface for LLM text completion.

    Implementors must wrap their SDK inside complete() and return a plain
    string. All prompt engineering lives in the callers (digest/generator.py),
    not here.
    """

    model: str  # Each provider sets this in __init__ to the active model slug

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """
        Sends a two-part prompt to the model and returns the generated text.

        Args:
            system_prompt: Sets the model's role / behaviour rules.
            user_prompt:   The actual content or task for this call.

        Returns:
            The model's response as a plain string (no SDK wrappers).

        Raises:
            LLMError: On API failure, rate-limit, or unexpected response.
        """
        ...


class LLMError(Exception):
    """
    Raised when an LLM provider call fails for any reason
    (API error, timeout, empty response, etc.).
    """
    pass
