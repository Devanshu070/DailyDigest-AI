"""
Factory function to instantiate the correct LLM provider based on config.

Usage (in runner.py):
    from app.llm import get_provider
    llm = get_provider()           # reads LLM_PROVIDER from env
    result = llm.complete(system, user)
"""

import os

from app.llm.base import BaseLLMProvider, LLMError

__all__ = ["get_provider", "BaseLLMProvider", "LLMError"]


def get_provider() -> BaseLLMProvider:
    """
    Instantiates and returns the configured LLM provider.

    Reads the LLM_PROVIDER environment variable:
        "groq"      → GroqProvider      (default — free, ~800 tok/s)
        "openai"    → OpenAIProvider    (GPT-4o / gpt-4o-mini)
        "anthropic" → AnthropicProvider (Claude — kept for future use)

    Raises:
        LLMError: If LLM_PROVIDER is set to an unknown value.
    """
    provider_name = os.environ.get("LLM_PROVIDER", "groq").lower().strip()

    if provider_name == "groq":
        from app.llm.groq import GroqProvider
        return GroqProvider()
    elif provider_name == "openai":
        from app.llm.openai import OpenAIProvider
        return OpenAIProvider()
    elif provider_name == "anthropic":
        from app.llm.anthropic import AnthropicProvider
        return AnthropicProvider()
    else:
        raise LLMError(
            f"Unknown LLM_PROVIDER '{provider_name}'. "
            "Valid values are: 'groq', 'openai', 'anthropic'."
        )
