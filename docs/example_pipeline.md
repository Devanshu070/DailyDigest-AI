# DailyDigest-AI — Example Pipeline Walkthrough

This document illustrates how data moves through the pipeline from ingestion to email delivery using representative examples. It defines expected transformation quality, demonstrates processing lifecycle transitions, and serves as a reference for prompt behavior and regression comparison.

> **About these examples.** All examples are intentionally abbreviated and simplified. Their purpose is to demonstrate expected transformations, processing behavior, and output quality — not to define exact wording or formatting. Both prompt phrasing and output style may evolve over time as the system is tuned.

This is not an implementation guide.

---

## 1. Example Source Inputs

The ingester parses RSS/Atom feed entries. Below are representative inputs for the two supported source types.

### Blog RSS Entry (Anthropic Blog)

```
title:        "Introducing Claude 4"
url:          https://www.anthropic.com/news/claude-4
published_at: 2025-05-08T14:00:00Z
source:       Anthropic Blog
```

### YouTube RSS Entry (Lex Fridman)

```
title:        "Sam Altman: OpenAI, GPT-5, Superintelligence"
url:          https://www.youtube.com/watch?v=abc123
published_at: 2025-05-07T18:30:00Z
source:       Lex Fridman (YouTube)
description:  Sam Altman returns to talk about GPT-5, the path to 
              superintelligence, safety research at OpenAI, and what 
              it actually feels like to be at the center of the AI moment.
```

After a successful fetch, both articles are written to the database with `processing_status = fetched`.

---

## 2. Raw Content → Cleaned Content

Cleaning removes boilerplate, navigation text, cookie banners, author bios, related-article links, and other non-substantive content. The goal is to retain only the informational body of the article.

### Raw Content (abbreviated)

```
Home | Blog | Research | About | Careers

Introducing Claude 4 · Published May 8, 2025 · 8 min read

[Contents: What's new · Benchmarks · Availability · Pricing]

Today we're announcing Claude 4, our most capable model to date.
Claude 4 represents a significant step forward in reasoning,
instruction-following, and code generation...

[Subscribe to our newsletter] [← Previous post] [Next post →]
© 2025 Anthropic. All rights reserved. Privacy Policy · Terms
```

### Cleaned Content

```
Introducing Claude 4

Today we're announcing Claude 4, our most capable model to date.

Claude 4 represents a significant step forward in reasoning, 
instruction-following, and code generation. In our internal evaluations, 
Claude 4 outperforms all prior Claude models across every benchmark we track...
```

`content_hash` is computed from the cleaned content. `token_count` is populated. `processing_status` advances to `cleaned`.

---

## 3. Step 1 — Per-Article Summarization

Each cleaned article is summarized individually. The prompt is content-agnostic — no user interests, no system context. The model decides length based on the substance of the content, capped at 300 words.

### Prompt sent to LLM

```
Write as much as this content deserves. If the key insight can be 
captured in 2-3 sentences, do that. If there is genuinely a lot of 
interesting substance, write more. Never pad. Never truncate something 
interesting just to keep it short. Maximum 300 words.

[Article content]
Introducing Claude 4

Today we're announcing Claude 4, our most capable model to date.

Claude 4 represents a significant step forward in reasoning, 
instruction-following, and code generation...
```

### Summary output — short article (2-3 sentences sufficient)

```
Anthropic released Claude 4, citing improvements in reasoning, 
instruction-following, and code generation across all internal benchmarks. 
No specific benchmark numbers are disclosed in this announcement post.
```

### Summary output — substantive article (more detail warranted)

```
Anthropic released Claude 4, describing it as their most capable model 
to date. The announcement highlights three areas of improvement: 
multi-step reasoning, instruction-following fidelity, and code generation 
quality. Anthropic notes that Claude 4 outperforms all prior Claude models 
across their internal benchmark suite, though specific figures are not 
included in this post.

The release also introduces changes to how Claude handles ambiguous 
instructions — defaulting to asking clarifying questions rather than 
making assumptions. This behavior is configurable via the system prompt 
for developers who prefer a more autonomous response style.

Pricing and availability details are covered separately in the linked 
product page.
```

The summary is stored in the `summary` field alongside (but separately from) `cleaned_content`. `summary_model` is recorded. `processing_status` advances to `summarized`.

> **Key property:** The summary reflects the article. It contains no inference about whether the user would find this interesting. That judgment is deferred entirely to Step 2.

> **Why store summaries separately from cleaned content:** Summaries are persisted independently so the digest can be regenerated — or the prompt iterated — without repeating the per-article LLM calls. Summarization is the most expensive per-unit step in the pipeline; storing the result makes it reusable across runs.

---

## 4. Step 2 — Digest Assembly

The digest assembler collects all `summarized` articles, reads `user_interests.md` from disk, and makes a single LLM call. Personalization — deciding what to include, what to skip, and how to frame each snippet — happens only here.

### Prompt structure (abbreviated)

```
System:
You are a personal AI research assistant.
The user's interests: [contents of user_interests.md]

Rules for the digest:
- Only include articles genuinely worth the user's attention
- Do not pad. On a quiet news day, 3 good snippets is better than 8 mediocre ones
- Each snippet should contain actual insight and specific details,
  not just a restatement of the headline
- Format in Markdown with clear section breaks between snippets

User:
Here are today's article summaries:

[Article 1]
  Source: Anthropic Blog
  URL: https://www.anthropic.com/news/claude-4
  Summary: Anthropic released Claude 4, describing it as their most
           capable model to date...

[Article 2]
  Source: Lex Fridman (YouTube)
  URL: https://www.youtube.com/watch?v=abc123
  Summary: Sam Altman discusses GPT-5 development timelines...

[Article 3]
  Source: VentureBeat
  URL: https://venturebeat.com/ai/...
  Summary: A startup raised $10M for an AI-powered scheduling tool...
```

### Digest output (Markdown)

```markdown
## Claude 4 is out — reasoning and code generation are the headline improvements

Anthropic released Claude 4 today. The announcement focuses on three 
areas: multi-step reasoning, instruction-following, and code generation. 
One notable behavioral change: Claude 4 now defaults to asking 
clarifying questions on ambiguous instructions rather than guessing — 
configurable via system prompt for developers who want less friction.

No benchmark numbers are in the announcement post itself, but a linked 
research page reportedly has more detail.

[Anthropic Blog](https://www.anthropic.com/news/claude-4)

---

## Sam Altman on GPT-5, superintelligence timelines, and what's actually hard

Lex Fridman's latest conversation with Sam Altman covers GPT-5 
development, Altman's evolving view on superintelligence timelines, 
and a candid discussion of what problems OpenAI has found genuinely 
difficult versus what turned out to be easier than expected. Worth 
watching for the second half — the conversation gets specific.

[Lex Fridman (YouTube)](https://www.youtube.com/watch?v=abc123)
```

> **Note:** Article 3 (the $10M scheduling startup) was omitted by the model as not relevant to the user's stated interests. This is expected behavior — the digest should reflect genuine relevance, not article count.

Both the Markdown output and its HTML conversion are stored on the `daily_digests` record.

---

## 5. Processing Lifecycle State Transitions

The table below shows how a representative article moves through `processing_status` during a normal pipeline run.

| Time | Event | `processing_status` | Notes |
|---|---|---|---|
| T+0 | Article fetched from RSS feed | `fetched` | `raw_content` stored |
| T+1 | Noise removed, token count populated | `cleaned` | `cleaned_content` and `token_count` written |
| T+2 | Step 1 LLM call completes | `summarized` | `summary` and `summary_model` written |
| T+3 | Included in digest assembly | `included_in_digest` | Terminal state for this run |

For an article that fails at the summarization stage:

| Time | Event | `processing_status` | Notes |
|---|---|---|---|
| T+0 | Article fetched | `fetched` | |
| T+1 | Cleaning completes | `cleaned` | |
| T+2 | Step 1 LLM call fails | `failed` | `processing_error` written; `retry_count` incremented; `last_retry_at` set |

> **Idempotency:** Re-running the pipeline does not duplicate completed work. Articles already at `summarized` or `included_in_digest` are not reprocessed. Each stage queries only for articles in the expected input status, so partial runs resume cleanly from where they left off.

---

## 6. Failure and Retry Scenario

### Scenario: one source fails to ingest, one article fails to summarize

**Pipeline run — ingestion phase:**

```
[INFO]  Ingesting: Anthropic Blog          ✓  3 new articles
[INFO]  Ingesting: Lex Fridman (YouTube)   ✓  1 new article
[ERROR] Ingesting: VentureBeat             ✗  Connection timeout
        failure_count → 2
        last_error → "httpx.ConnectTimeout after 10s"
[INFO]  Ingestion complete. 3/4 sources succeeded.
```

The pipeline continues with the 4 articles that were successfully ingested. VentureBeat's `failure_count` is incremented and `last_error` is updated on the source record.

**Pipeline run — summarization phase:**

```
[INFO]  Summarizing article abc-001        ✓
[INFO]  Summarizing article abc-002        ✓
[INFO]  Summarizing article abc-003        ✓
[ERROR] Summarizing article abc-004        ✗  LLM rate limit exceeded
        processing_status → failed
        processing_error → "RateLimitError: 429 Too Many Requests"
        retry_count → 1
        last_retry_at → 2025-05-08T07:03:12Z
[INFO]  Summarization complete. 3/4 articles summarized.
```

The 3 successfully summarized articles proceed to digest assembly. Article `abc-004` remains in the database with `processing_status = failed` and will be eligible for retry logic in a future run.

**Email status footer (reflecting the run):**

```
3 of 4 sources ingested successfully.
Failed source: VentureBeat (Connection timeout — 2nd consecutive failure)

3 of 4 articles summarized successfully.
1 article failed summarization and was excluded from today's digest.
```

---

## 7. Example Final Email Digest Structure

The email is delivered as HTML, converted from the LLM's Markdown output. The structure below shows the expected layout.

```
Subject: Your AI Digest — May 8, 2025

──────────────────────────────────────────

  Your AI Digest
  Thursday, May 8, 2025

──────────────────────────────────────────

  Claude 4 is out — reasoning and code generation are the headline improvements

  Anthropic released Claude 4 today. The announcement focuses on three
  areas: multi-step reasoning, instruction-following, and code generation.
  One notable behavioral change: Claude 4 now defaults to asking
  clarifying questions on ambiguous instructions rather than guessing —
  configurable via system prompt for developers who want less friction.

  → Anthropic Blog

──────────────────────────────────────────

  Sam Altman on GPT-5, superintelligence timelines, and what's actually hard

  Lex Fridman's latest conversation with Sam Altman covers GPT-5
  development, Altman's evolving view on superintelligence timelines,
  and a candid discussion of what problems OpenAI has found genuinely
  difficult versus what turned out to be easier than expected.

  → Lex Fridman (YouTube)

──────────────────────────────────────────

  3 of 4 sources ingested successfully.
  Failed: VentureBeat (connection timeout — 2nd consecutive failure)

  1 article failed summarization and was excluded from today's digest.

──────────────────────────────────────────
```

The footer is always present and always accurate. It surfaces operational state without interrupting the reading experience.
