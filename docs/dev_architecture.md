# DailyDigest-AI — Developer Architecture

This document explains how DailyDigest-AI executes at runtime from ingestion to email delivery. It serves as quick reference.

For design philosophy, see [`architecture.md`](./architecture.md).

---

## 1. Runtime Pipeline

```
┌──────────────────────────────────────────────────────────────────────┐
│  Ingestion Layer  (app/ingestion/)                                   │
│  fetches content based on enabled sources from the `sources` table   │
│  · YouTube · blogs · newsletters · RSS  (RSS-first, HTML fallback)   │
│  · parse entries per source type                                     │
│  · deduplicate by URL + content_hash                                 │
│  · per-source failure isolation                                      │
└──────────────────────────────────────────────────────────────────────┘
        │
        ▼  writes: raw_content, metadata
        │  status:  → fetched
        │
        ▼
┌────────────────────────────────────────────────┐
│  Content Cleaning Layer  (app/processing/)     │
│  normalizes raw content for LLM processing     │
│  · HTML strip · transcript normalize           │
│  · boilerplate removal · token estimation      │
└────────────────────────────────────────────────┘
        │
        ▼  writes: cleaned_content, content_hash, token_count
        │  status:  fetched → cleaned
        │
        ▼
┌──────────────────────────────────────────────────┐
│  Summarization Layer  (app/digest/generator.py)  │
│  Step 1 — per-article, content-agnostic          │
│  no user context — summary reflects the article  │
└──────────────────────────────────────────────────┘
        │
        ▼
  Summarization Router
        │
   ┌────┴────────────────────────────────┐
   │                                     │
   ▼                                     ▼
Standard                            Hierarchical
(blogs · newsletters                (large transcripts:
 · short transcripts)                token_count > threshold)
   │                                     │
single LLM call                     chunk1 → summary1
cleaned_content → summary           chunk2 + summary1 → summary2
                                    chunk3 + context  → summary3
                                    ...
                                    final synthesis → summary
   │                                     │
   └──────────────┬──────────────────────┘
                  ▼
        writes: summary, summary_model
        status: cleaned → summarized
                  │
                  ▼
┌──────────────────────────────────────────────────────┐
│  Digest Assembly Layer  (app/digest/generator.py)    │
│  Step 2 — personalized via user_interests.md         │
│  · single LLM call over all article summaries        │
│  · selects up to 10 high-value articles              │
│  · markdown output → converted to HTML               │
└──────────────────────────────────────────────────────┘
                  │
                  ▼
        writes: daily_digests (markdown_content + html_content)
        status: summarized → included_in_digest
                  │
                  ▼
┌────────────────────────────────────────────┐
│  Email Delivery Layer  (app/email/)        │
│  sends the final digest to the inbox       │
│  · html_content → Resend API → inbox       │
└────────────────────────────────────────────┘
                  │
                  ▼
        writes: daily_digests.sent_at
                  │
                  ▼
        Structured logs + pipeline summary
```

---

## 2. Article Lifecycle

```
fetched → cleaned → summarized → included_in_digest
                 ↘            ↘
                          failed  ← any stage
```

| Status               | Written by | Key columns written                                 |
|----------------------|------------|-----------------------------------------------------|
| `fetched`            | Ingestion  | `raw_content`, `scraped_at`, `published_at`         |
| `cleaned`            | Cleaner    | `cleaned_content`, `content_hash`, `token_count`    |
| `summarized`         | Step 1 LLM | `summary`, `summary_model`                          |
| `included_in_digest` | Step 2 LLM | status only                                         |
| `failed`             | Any stage  | `processing_error`, `retry_count`, `last_retry_at`  |

> Stages always query by `processing_status` — never infer state from field values.
> Chunking is an internal runtime strategy, not a lifecycle state.

---

## 3. Module Responsibilities

| Module                          | Owns                                            | Does NOT own           |
|---------------------------------|-------------------------------------------------|------------------------|
| `app/ingestion/`                | Fetch from `sources` table · parse · dedup      | Cleaning · LLM calls   |
| `app/processing/cleaner.py`     | HTML strip · normalize · token estimate         | LLM calls · I/O        |
| `app/llm/`                      | `BaseLLMProvider.complete()` · providers        | Business logic         |
| `app/digest/generator.py`       | Step 1 summarization · Step 2 assembly          | Email · ingestion      |
| `app/email/sender.py`           | Markdown → HTML · Resend delivery               | Articles · summaries   |
| `app/models/`                   | ORM models · enums · `TimestampMixin`           | Business logic         |
| `app/runner.py`                 | Pipeline sequencing only                        | Scraping · LLM · email |
| `app/utils/`                    | Hashing · retry · text utilities                | Domain logic           |
| `app/prompts/user_interests.md` | User interest profile — Step 2 only             | —                      |
| `scripts/`                      | One-off operational scripts                     | Pipeline stages        |

---

## 4. Database Tables

| Table           | Role                        | Key tracking fields                                           |
|-----------------|-----------------------------|-----------------------------------------------------------------|
| `sources`       | Source registry + health    | `failure_count`, `last_error`, `last_fetched_at`              |
| `articles`      | Full content lifecycle      | `processing_status`, `token_count`, `summary`, `retry_count`  |
| `daily_digests` | Pipeline output — 1 row/day | `markdown_content`, `html_content`, `sent_at`                 |

> All tables share `created_at` / `updated_at` via `TimestampMixin`.

---

## 5. Two LLM Steps

|                   | Step 1 — Summarization          | Step 2 — Digest Assembly                     |
|-------------------|---------------------------------|----------------------------------------------|
| **Reads**         | `article.cleaned_content`       | All `article.summary` + `user_interests.md`  |
| **System prompt** | None                            | User interests                               |
| **Output**        | `article.summary` (≤ 300 words) | `daily_digests.markdown_content`             |
| **Personalized?** | ❌ No                           | ✅ Yes                                       |
| **LLM calls**     | One per article                 | One total                                    |
| **Status after**  | `summarized`                    | `included_in_digest`                         |

> User interests enter **only** at Step 2 — summaries are content-agnostic, stable, and reusable across runs.

---

## 6. Hierarchical Summarization

> Triggered when `token_count > threshold`. Used for long YouTube transcripts.
> **Not RAG** — no vector DB, no retrieval, all in-memory within a single run.

**Why not naive chunking:**
```
chunk 1  establishes key concept
  ...
chunk 8  references it briefly
         ← isolated chunk 8 loses that dependency
```

**Hierarchical approach:**
```
chunk1                       → summary1
chunk2 + summary1            → summary2
chunk3 + [compressed memory] → summary3
...
final synthesis              → article summary
```

Goal: preserve narrative continuity · concept persistence · conversational context across the full transcript.

---

## 7. Failure Handling

| Scope                 | Behavior                                            | State change                                             |
|-----------------------|-----------------------------------------------------|----------------------------------------------------------|
| Source failure        | Log + increment `failure_count`, pipeline continues | `sources.failure_count++`, `last_error` written          |
| Article summarization | Article skipped for this run                        | `processing_status → failed`, `processing_error` written |
| Digest assembly       | Run ends, no email sent                             | Summarized articles remain, safe to rerun                |
| Email delivery        | Digest already in DB, no data lost                  | `sent_at` not written; resend without regenerating       |

> Already-`summarized` or `included_in_digest` articles are never reprocessed on rerun.

---

## 8. Observability

| Stage           | Signals emitted                                                         |
|-----------------|-------------------------------------------------------------------------|
| Ingestion       | Fetch duration · articles ingested · source failures                    |
| Processing      | Token count per article · cleaning duration                             |
| Summarization   | LLM latency · retry count · routing decision (standard / hierarchical)  |
| Digest assembly | Article count included · generation duration                            |
| Email           | Send status · delivery failure                                          |
| Run summary     | All-stage totals — emitted at pipeline completion                       |

> Structured output (key-value / JSON) throughout — supports future log aggregation without format changes.

---

## 9. Where Does This Belong?

| Adding...                          | Goes in...                                              |
|------------------------------------|---------------------------------------------------------|
| New source type                    | `app/ingestion/` — implement `BaseIngester`             |
| New LLM provider                   | `app/llm/` — implement `BaseLLMProvider`                |
| Shared helper (hash · retry · text)| `app/utils/`                                            |
| Schema change                      | `app/models/` + new migration in `migrations/versions/` |
| Prompt / interest tuning           | `app/prompts/user_interests.md`                         |
| Summarization or digest logic      | `app/digest/generator.py`                               |
| Email formatting or delivery       | `app/email/sender.py`                                   |
| Pipeline sequencing                | `app/runner.py`                                         |
| One-off operational task           | `scripts/`                                              |

---

## 10. Operational Invariants

```
✗  Never use raw_content as LLM input — always cleaned_content
✗  Never inject user interests into Step 1
✗  Never pass cleaned_content to digest assembly — summaries only
✗  Never let one source failure abort the pipeline
✗  Never reprocess articles already at summarized or included_in_digest
✗  Never run migrations inside the pipeline — manual pre-start step only
✓  Always query pipeline stages by processing_status
✓  Always persist to DB before advancing to the next stage
```

---

## 11. Future Expansion

| Feature           | Inserts after | Notes                                              |
|-------------------|---------------|----------------------------------------------------|
| Relevance scoring | Step 1        | Pre-filter before digest assembly                  |
| Topic clustering  | Step 1        | New `clustered` status                             |
| Embeddings        | `summarized`  | Embed `summary`, store vector on `articles`        |
| Semantic search   | —             | Read-only query layer over stored embeddings       |
| Multi-user        | —             | `users` table; parameterize interests + recipient  |
| Async ingestion   | Runner        | Replace synchronous source loop                    |
| New source types  | Ingestion     | Implement `BaseIngester` in `app/ingestion/`       |

> All future enhancements — none are part of the MVP architecture.
