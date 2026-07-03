"""
LLM provider module.

Exposes two pre-initialized, ready-to-use provider instances:
    llm_summarizer — fast/cheap model for reading long transcripts
    llm_assembler  — smart/large model for reasoning & digest filtering

Usage (in runner.py):
    from app.llm import llm_summarizer, llm_assembler
"""

import os

from app.llm.base import BaseLLMProvider, LLMError

__all__ = ["llm_summarizer", "llm_assembler", "get_provider", "BaseLLMProvider", "LLMError"]

# ---------------------------------------------------------------------------
# Model selection
# ---------------------------------------------------------------------------
_MODEL_SUMMARIZER = "meta-llama/llama-4-scout-17b-16e-instruct"  # fast, cheap — for reading long transcripts
_MODEL_ASSEMBLER  = "openai/gpt-oss-120b"                        # smart, large — for reasoning & filtering


def get_provider(provider_name: str | None = None, model: str | None = None) -> BaseLLMProvider:
    """
    Instantiates and returns the configured LLM provider.

    Reads the LLM_PROVIDER environment variable:
        "groq"      → GroqProvider      (default — free, ~800 tok/s)
        "openai"    → OpenAIProvider    (GPT-4o / gpt-4o-mini)
        "anthropic" → AnthropicProvider (Claude — kept for future use)

    Raises:
        LLMError: If the requested provider is unknown.
    """
    provider_name = (provider_name or os.environ.get("LLM_PROVIDER", "groq")).lower().strip()

    if provider_name == "groq":
        from app.llm.groq import GroqProvider
        return GroqProvider(model=model)
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


# Pre-initialized instances — import these directly instead of calling get_provider()
llm_summarizer: BaseLLMProvider = get_provider("groq", model=_MODEL_SUMMARIZER)
llm_assembler: BaseLLMProvider  = get_provider("groq", model=_MODEL_ASSEMBLER)
