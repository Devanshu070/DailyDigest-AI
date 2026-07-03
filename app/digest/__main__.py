# %%
"""
Test runner for the LLM layer and digest pipeline.

Runs three tests in order:
  1. LLM Provider ping — verifies GROQ_API_KEY and basic connectivity
  2. Standard summarization — single-pass summary of a short article
  3. Digest assembly — multi-article digest with user interests

Edit the TEST_* constants below to try different inputs.
Run with:
    uv run python -m app.digest
"""

from app.llm import get_provider
from app.digest.summarizer import summarize_article
from app.digest.assembler import generate_digest
from app.digest.models import ArticleSummaryInput

SEP = "=" * 60

# ---------------------------------------------------------------------------
# Test inputs — edit these to try different content
# ---------------------------------------------------------------------------

TEST_ARTICLE_SHORT = ArticleSummaryInput(
    title="Meta releases Llama 3.3 70B",
    url="https://ai.meta.com/blog/llama-3-3",
    source_name="Meta AI Blog",
    cleaned_content=(
        "Meta has released Llama 3.3 70B, a new open-weight model that outperforms "
        "its 405B predecessor on most benchmarks while being significantly cheaper to run. "
        "The model was trained on over 15 trillion tokens and supports a 128k context window. "
        "It achieves state-of-the-art results on MMLU, HumanEval, and GSM8K, beating "
        "GPT-4o-mini on several coding tasks. Meta released it under a permissive license "
        "allowing commercial use. The weights are available on Hugging Face."
    ),
    token_count=120,
)

TEST_ARTICLE_2 = ArticleSummaryInput(
    title="OpenAI announces o3 reasoning model",
    url="https://openai.com/blog/o3",
    source_name="OpenAI Blog",
    cleaned_content=(
        "OpenAI has unveiled o3, its most powerful reasoning model to date. "
        "The model scored 87.5% on the ARC-AGI benchmark, a significant leap from "
        "o1's 32%. o3 uses a novel 'chain of thought' search process during inference, "
        "spending more compute on harder problems. It is not yet publicly available and "
        "will go through a safety evaluation period before release. OpenAI says o3 "
        "represents a qualitative jump in reasoning ability rather than just a scaling improvement."
    ),
    token_count=110,
)

# Simulated massive transcript to trigger hierarchical summarization (>12k chars)
TEST_ARTICLE_LONG_TEXT = (
    "Welcome back to the podcast. Today we are talking about AI and scaling laws. "
    "The core idea is that if you throw more compute and data at a transformer, it gets better. "
    "But we are hitting a wall where high-quality human data is running out. "
    "Researchers are now looking at synthetic data generation. "
    "Let's dive deep into how models evaluate their own outputs. "
) * 80  # ~21,000 characters

TEST_ARTICLE_LONG = ArticleSummaryInput(
    title="Simulated Long Podcast (Scaling Laws)",
    url="https://youtube.com/watch?v=mock",
    source_name="Mock AI Podcast",
    cleaned_content=TEST_ARTICLE_LONG_TEXT,
    token_count=7000,  # Forces hierarchical
)


# ---------------------------------------------------------------------------
# Test 1 — LLM Provider Ping
# ---------------------------------------------------------------------------

def test_llm_ping(llm):
    print(f"\n\n{SEP}")
    print("TEST 1: LLM Provider Ping")
    print(SEP)
    response = llm.complete(
        system_prompt="You are a test assistant. Respond only with 'OK'.",
        user_prompt="Are you working?",
    )
    print(f"Provider: {type(llm).__name__}")
    print(f"Model:    {getattr(llm, 'model', 'unknown')}")
    print(f"Response: {response}")


# ---------------------------------------------------------------------------
# Test 2 — Standard Summarization
# ---------------------------------------------------------------------------

def test_standard_summarize(llm_summarizer):
    print(f"\n\n{SEP}")
    print("TEST 2: Standard Summarization")
    print(SEP)
    print(f"Input article: '{TEST_ARTICLE_SHORT.title}'")
    print(f"Input length:  {len(TEST_ARTICLE_SHORT.cleaned_content)} chars, ~{TEST_ARTICLE_SHORT.token_count} tokens")

    summary = summarize_article(TEST_ARTICLE_SHORT, llm_summarizer)

    print(f"\nSUMMARY OUTPUT ({len(summary)} chars):")
    print("-" * 40)
    print(summary)
    return summary


# ---------------------------------------------------------------------------
# Test 2.5 — Hierarchical Summarization
# ---------------------------------------------------------------------------

def test_hierarchical_summarize(llm_summarizer):
    print(f"\n\n{SEP}")
    print("TEST 2.5: Hierarchical Summarization")
    print(SEP)
    print(f"Input article: '{TEST_ARTICLE_LONG.title}'")
    print(f"Input length:  {len(TEST_ARTICLE_LONG.cleaned_content)} chars, ~{TEST_ARTICLE_LONG.token_count} tokens")
    
    print("\nStarting hierarchical chunking process...")
    # This will trigger our new print statements inside summarizer.py
    summary = summarize_article(TEST_ARTICLE_LONG, llm_summarizer)
    return summary


# ---------------------------------------------------------------------------
# Test 3 — Digest Assembly
# ---------------------------------------------------------------------------

def test_digest_assembly(llm_summarizer, llm_assembler, summary_1: str):
    print(f"\n\n{SEP}")
    print("TEST 3: Digest Assembly")
    print(SEP)

    # Generate a summary for article 2 as well
    print(f"Summarizing article 2: '{TEST_ARTICLE_2.title}'...")
    summary_2 = summarize_article(TEST_ARTICLE_2, llm_summarizer)

    articles = [TEST_ARTICLE_SHORT, TEST_ARTICLE_2]
    summaries = [summary_1, summary_2]

    print(f"\nAssembling digest from {len(articles)} articles...")
    digest = generate_digest(articles, summaries, llm_assembler)

    print(f"\nDIGEST OUTPUT (model={digest.model_used}, prompt_version={digest.prompt_version}):")
    print("-" * 40)
    print(digest.markdown_content)
    print(f"\n--- HTML snippet (first 300 chars) ---")
    print(digest.html_content[:300])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import os
    print("DailyDigest — LLM Pipeline Test Runner")
    print("Initializing LLM providers...")

    try:
        llm_summarizer = get_provider("groq", model=os.environ.get("GROQ_MODEL_SUMMARIZER"))
        llm_assembler  = get_provider("groq", model=os.environ.get("GROQ_MODEL_ASSEMBLER"))
    except Exception as exc:
        print(f"\nFAILED to initialize LLM provider: {exc}")
        print("Make sure API keys are set in your .env file.")
        return

    try:
        test_llm_ping(llm_summarizer)
        test_llm_ping(llm_assembler)
    except Exception as exc:
        print(f"Test 1 FAILED: {exc}")
        return  # No point continuing if the provider itself is broken

    summary_1 = None
    try:
        summary_1 = test_standard_summarize(llm_summarizer)
    except Exception as exc:
        print(f"Test 2 FAILED: {exc}")

    if summary_1:
        try:
            test_hierarchical_summarize(llm_summarizer)
        except Exception as exc:
            print(f"Test 2.5 FAILED: {exc}")

        try:
            test_digest_assembly(llm_summarizer, llm_assembler, summary_1)
        except Exception as exc:
            print(f"Test 3 FAILED: {exc}")

    print(f"\n\n{SEP}")
    print("All tests complete.")
    print(SEP)


if __name__ == "__main__":
    main()
# %%
