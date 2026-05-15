# DailyDigest-AI — Architecture Reference

This document describes the conceptual architecture of DailyDigest-AI: why the system is designed the way it is, how data moves through it, and how the design supports future evolution. It is intended as a stable reference for contributors and maintainers, not as a setup guide or implementation tutorial.

---

## 1. System Overview

DailyDigest-AI is a scheduled pipeline that ingests content from AI-focused sources (YouTube channels, blogs, RSS feeds), processes each article through a two-step LLM pipeline, assembles a personalized digest, and delivers it via email.

The system runs once per day, triggered externally by a cron schedule. It has no web server, no API surface, and no interactive components. Its only outputs are records written to a PostgreSQL database and an email delivered to a recipient. The system is intentionally batch-oriented rather than event-driven or real-time.

The architecture is a **modular monolith**: a single Python process organized into well-separated internal modules. This trades the operational complexity of microservices for simplicity appropriate to a single-user, single-purpose system — while preserving the internal boundaries needed to evolve individual components independently.

---

## 2. Non-Goals

The current architecture intentionally does not include:

- real-time or streaming ingestion
- microservices or distributed task queues
- semantic clustering or vector databases
- multi-user support
- live APIs or web dashboards

These are deferred to preserve operational simplicity at MVP scale.

---

## 3. Architectural Principles

**State-driven processing.** Every article carries an explicit `processing_status` that moves forward through a defined lifecycle. The pipeline never infers where an article is by looking at which fields are populated — it reads the status field. This makes the system inspectable, resumable, and debuggable without reconstructing intent from data.

**Separation of concerns across LLM steps.** Summarization and digest assembly are distinct operations with different responsibilities. Summarization is content-focused and provider-agnostic. Digest assembly is user-focused and interest-aware. Conflating them into a single prompt would make the system harder to tune, harder to reason about, and harder to evolve independently.

**Resilience over atomicity.** A failure in one source should never abort the pipeline. The system is designed to accumulate partial results gracefully and deliver a digest from whatever succeeded, rather than treating the run as an atomic all-or-nothing operation.

**Deduplication by content identity, not timing.** Articles are deduplicated on URL and on a hash of their cleaned content. This means re-running the pipeline does not produce duplicate records, and content syndicated across multiple sources is handled cleanly at the ingestion layer.

**Provider abstraction.** The LLM provider is an interchangeable dependency, not a hardcoded choice. All LLM calls flow through a common interface. Switching providers requires only a configuration change — no code changes and no prompt rewrites.

**Manual schema management.** Database migrations are applied manually via Alembic before the pipeline runs. The pipeline itself never modifies the schema. This makes deployments explicit and safe, and keeps the pipeline's runtime responsibilities narrow.

---

## 4. High-Level Data Flow

```
External Sources
  (YouTube RSS, Blog RSS, HTML)
         │
         ▼
   [ Ingestion ]
   Fetch → deduplicate → store raw + cleaned content
         │
         ▼
  [ Step 1: Summarization ]
  cleaned_content → LLM → summary
  (per article, content-agnostic)
         │
         ▼
  [ Step 2: Digest Assembly ]
  all summaries → LLM → digest markdown
  (personalized via user_interests.md)
         │
         ▼
  [ Email Delivery ]
  markdown → HTML → Resend → inbox
         │
         ▼
  [ PostgreSQL ]
  articles, summaries, digest all persisted
```

Data enters the system as raw scraped content. It is cleaned, summarized independently of user preferences, then assembled into a personalized digest in a second LLM pass. Both the raw content and each transformation stage are preserved in the database.

---

## 5. Core Components and Responsibilities

### `app/ingestion/`
Responsible for fetching content from external sources and writing new article records to the database. Ingesters are source-type-specific but implement a shared abstract interface. Ingestion is the only component that communicates with the external internet during a pipeline run.

### `app/processing/`
Responsible for transforming raw fetched content into clean, normalized text ready for LLM processing. `cleaner.py` handles HTML stripping, transcript normalization, boilerplate removal, whitespace cleanup, and token estimation. This is a deterministic, non-LLM step that runs between ingestion and summarization.

### `app/llm/`
Provides a single abstract interface (`BaseLLMProvider.complete(system_prompt, user_prompt) -> str`) with concrete implementations for supported providers. The rest of the system depends only on the abstract interface. The active provider is selected at startup from configuration.

### `app/digest/generator.py`
Orchestrates the two-step LLM pipeline. It reads from the database, constructs prompts, calls the LLM provider, writes results back to the database, and advances article status. It does not know which LLM provider is in use.

### `app/email/sender.py`
Converts the markdown digest to HTML and delivers it via the Resend API. Email delivery is the final step and is fully isolated from digest generation — the sender receives a fully-formed digest record, not article data.

### `app/models/`
Defines the SQLAlchemy ORM models and the shared `TimestampMixin`. Models are the authoritative source of schema truth; Alembic migrations are generated from them.

### `app/runner.py`
The top-level orchestrator. It sequences ingestion, summarization, digest assembly, and email delivery. It collects failure information across the run and includes a status summary in the email footer. It has no LLM or email logic of its own.

### `app/config.py`
Loads all configuration from environment variables via `pydantic-settings`. It is the only place environment variables are read. A validator corrects the `postgres://` scheme injected by Render to the `postgresql://` scheme required by SQLAlchemy.

### `app/prompts/user_interests.md`
A plain text file read from disk at runtime during digest assembly. It is not stored in configuration or the database. Changing it requires no code change and no redeployment — only a file edit before the next run.

---

## 6. Database Architecture Philosophy

PostgreSQL is the system's single source of truth and its primary mechanism for state management and recoverability. Every meaningful processing stage writes a record or updates a field. Nothing is held only in memory across pipeline steps.

**Three tables serve three distinct purposes:**

- `sources` — configuration and health tracking for each content source
- `articles` — the full lifecycle of every piece of content from raw fetch through digest inclusion
- `daily_digests` — the output of each pipeline run, stored in both markdown and HTML

**A shared `TimestampMixin`** provides `created_at` and `updated_at` to every table. `updated_at` is auto-updated on every write. This is enforced at the ORM layer, not left to application code.

**Migrations are managed with Alembic from day one.** `Base.metadata.create_all()` is not used after the initial schema is established. All schema changes are versioned migrations, making the schema history auditable and deployments predictable.

**Content identity is hashed.** Each article stores a SHA256 hash of its `cleaned_content`. This provides a second deduplication mechanism beyond URL uniqueness, protecting against content that appears under different URLs.

---

## 7. Ingestion Pipeline

Ingestion is source-type-aware but structurally uniform. The pipeline reads all active records from the `sources` table at runtime — each record defines a source URL, type, and fetch strategy. Content is fetched dynamically from those configured sources, not from hardcoded URLs. All ingesters follow the same pattern: fetch a feed, parse entries, deduplicate against existing records, and write new articles with `processing_status = fetched`.

**RSS-first strategy.** The ingester attempts to consume an RSS or Atom feed before falling back to HTML scraping. Most target sources (OpenAI blog, Anthropic blog, Google DeepMind, YouTube channels) publish RSS feeds. Newsletters follow the same flow as blogs — RSS-first, HTML fallback. The fallback HTML scraper uses `trafilatura`, which is purpose-built for content extraction and produces cleaner text than generic parsers.

**YouTube is a first-class source type.** YouTube channels expose a standard RSS feed at a predictable URL derived from the channel ID. The YouTube ingester uses this feed directly — no scraping, no API quota consumption. YouTube transcripts may be significantly larger than typical blog articles; the processing and summarization stages account for this.

**Per-source failure isolation.** Each source is ingested inside an independent error boundary. A failed source increments `failure_count`, records the error in `last_error`, and updates `last_fetched_at`. The pipeline continues to the next source. A source's failure history is visible in the database and surfaced in the digest email footer.

**Deduplication at write time.** New articles are inserted only if their URL does not already exist in the database. The unique constraint on `url` is enforced at the database level, not just in application code. `content_hash` provides a secondary guard against content duplication across sources.

MVP ingestion runs synchronously. Async ingestion may be introduced later if source volume or latency warrants it.

---

## 8. Two-Step LLM Processing Pipeline

The LLM pipeline is deliberately split into two sequential, independent steps with different scopes of responsibility.

### Step 1 — Per-Article Summarization

Each article with `processing_status = cleaned` is summarized individually. The prompt is content-agnostic — no user interests, no system context. The model decides length based on the substance of the content, capped at 300 words. The summary reflects the article, not the reader.

The `summary_model` field records which model generated each summary. This is separate from `model_used` on `daily_digests`, which records the model used for digest assembly. This allows the two steps to use different models if needed, and makes the provenance of each field auditable.

**Standard path (blogs, newsletters, short transcripts):** A single LLM call with the full `cleaned_content`. This handles the majority of sources.

**Hierarchical path (very large content — long YouTube transcripts):** Long transcripts cannot be handled coherently in a single prompt pass. Naive chunking is explicitly avoided because:

- Later chunks may lack context established in earlier sections
- Conversational and transcript content has cross-section dependencies
- Isolated chunk summaries lose narrative continuity and can misrepresent the overall discussion

Instead, content is processed progressively: the first chunk is summarized independently; each subsequent chunk is summarized with context from prior processing — which may include compressed memory, the most recent chunk summary, or a running summary of earlier sections. A final pass synthesizes the result into one coherent article summary.

This is not RAG. No vector database is involved. No retrieval system is used. Chunking is a long-document processing strategy executed entirely in memory within a single pipeline run. The goal is to preserve narrative continuity, concept persistence, and evolving discussion context across the full length of the transcript.

### Step 2 — Digest Assembly

Once all articles are summarized, the digest assembler collects all records with `processing_status = summarized`, reads `user_interests.md` from disk, and makes a single LLM call. The system prompt carries the user's interests. The user prompt contains all article summaries with their source names and URLs.

User personalization enters the pipeline exactly here and nowhere earlier. The model is instructed to include only articles genuinely worth the user's attention, targeting up to 10 high-value articles per digest. On quieter days with less relevant content, fewer entries is correct — the digest prioritizes signal quality over a fixed length. The output is Markdown, which is converted to HTML for email delivery. Markdown is treated as the canonical LLM output representation because it is human-readable, diff-friendly, and easily transformable into other formats.

Both `markdown_content` and `html_content` are stored on the digest record. This means the digest can be re-rendered or re-sent without another LLM call, and the raw LLM output is always available for debugging or prompt iteration.

---

## 9. Processing Lifecycle and State Transitions

Every article moves through an explicit status field:

```
fetched → cleaned → summarized → included_in_digest
                                      ↑
                  (any stage can transition to) failed
```

- **`fetched`** — raw content has been stored; no cleaning or processing has occurred
- **`cleaned`** — noise has been removed; `token_count` is populated; ready for summarization
- **`summarized`** — LLM summary is written to `summary`; `summary_model` is recorded; ready for digest inclusion
- **`included_in_digest`** — article has been used in a digest; `processing_status` is terminal for this run
- **`failed`** — processing failed at some stage; `processing_error` records the reason; `retry_count` and `last_retry_at` track retry history

The pipeline queries by status at each stage. It never infers processing state from the presence or absence of field values. This makes it safe to restart a partially-completed run — each stage picks up exactly where the previous run left off, processing only articles in the appropriate status.

`retry_count` and `last_retry_at` on the `articles` table support future retry logic without schema changes. The fields are populated today but gating logic (e.g., skip after N retries) can be added incrementally.

---

## 10. Orchestration Flow

The runner is the single entry point for a pipeline execution. It sequences all stages in order:

1. **Ingest** all active sources, collecting failure information per source
2. **Summarize** all articles with status `cleaned` (Step 1 LLM)
3. **Assemble** the digest from all articles with status `summarized` (Step 2 LLM)
4. **Convert** the digest markdown to HTML
5. **Persist** the digest record with both representations, model metadata, and prompt version
6. **Deliver** the email with the digest HTML body and a status footer reporting how many sources succeeded and which failed
7. **Log** a full pipeline summary

The runner holds no business logic. Each step is delegated to the responsible module. The runner's only unique contribution is sequencing and failure aggregation — specifically, accumulating per-source failure information across the ingestion step and surfacing it in the email footer and pipeline log.

---

## 11. Failure Handling and Recovery Strategy

**Ingestion failures are isolated.** A source that fails to ingest does not interrupt the pipeline. The failure is recorded on the source record and reported at the end of the run. The pipeline continues with whatever was successfully ingested.

**Summarization failures are recorded per article.** An article that fails summarization transitions to `failed` with the error stored in `processing_error`. It is excluded from the current digest but remains in the database. Future runs can retry it by resetting its status or via dedicated retry logic.

**Digest assembly failure is terminal for the run.** If the digest LLM call fails, the run ends without sending an email. This is a single call over a well-bounded input (summaries, not full content), making it the least likely failure point in the pipeline.

**Email delivery failure does not corrupt state.** The digest record is written to the database before the email is sent. A delivery failure can be recovered by re-sending from the stored record without regenerating the digest.

**The database is the recovery surface.** Because every stage writes its results before advancing to the next, the system can be resumed after any failure by re-running the pipeline. Status fields ensure that completed work is not duplicated, and failed work is not silently skipped.

Pipeline stages are designed to be idempotent wherever possible — re-running the pipeline does not create duplicate records or repeat completed work.

---

## 12. Deployment Architecture

The system is deployed as a **Render Cron Job** — a managed, scheduled execution environment that runs the pipeline process on a defined schedule (`0 7 * * *`, 7am UTC daily) and terminates it when the process exits.

This model is a deliberate fit for the system's nature: it is a batch pipeline, not a long-running service. There is no benefit to keeping a process alive between runs, and the operational overhead of a managed cron is near zero.

The database is a **Render managed PostgreSQL** instance, linked to the cron job service. Render injects the connection string as an environment variable. A validator in `app/config.py` corrects the `postgres://` scheme Render uses to the `postgresql://` scheme required by SQLAlchemy — this is a known Render-specific issue handled transparently.

**Migrations are applied manually** before each deployment, not by the pipeline at runtime. This is a deliberate separation: schema changes are an operator action, not a side effect of running the pipeline.

For local development, the same pipeline is run manually against a Docker-managed PostgreSQL instance. There is no difference in pipeline behavior between local and production.

---

## 13. Future Extensibility

The architecture is designed to accommodate the following future capabilities without structural changes to the core pipeline:

**Topic clustering and deduplication.** The current design produces one digest snippet per article. A future iteration can introduce an embedding step between summarization and digest assembly — grouping articles that cover the same story into a single snippet. The `processing_status` enum can be extended with a `clustered` state. The digest assembly stage is structurally isolated from summarization, making future clustering or grouping logic possible without redesigning the ingestion or summarization pipeline.

**Relevance scoring and pre-digest ranking.** A ranking step between summarization and digest assembly could score each article's relevance to user interests before the digest LLM call. This would allow the assembler to work with a pre-filtered, prioritized set rather than the full day's content. Future implementations may include lightweight embeddings, semantic similarity scoring, or keyword-based ranking. These are future improvements only — not part of the MVP architecture.

**Semantic search and retrieval.** Article summaries and cleaned content are stable, structured data with consistent schemas. Adding a vector embedding column to `articles` and an embedding store enables semantic search over the article corpus without changing the pipeline's primary flow.

**Multi-user personalization.** The current system is single-user: `user_interests.md` is a single file and `DIGEST_RECIPIENT_EMAIL` is a single address. Extending to multiple users requires adding a `users` table, associating digests and interests with users, and parameterizing the digest assembly step. The LLM abstraction layer and digest generator are already structured to accept a user context without assuming it is a global singleton.

**Additional source types.** The `ingestion/` module has an abstract base interface. New source types (newsletters, Hacker News, arXiv, podcasts) add a new ingester class without touching existing ingesters or the pipeline orchestrator.

**LLM provider expansion.** The provider abstraction layer makes it straightforward to add new providers — Gemini, Mistral, local models via Ollama — by implementing `BaseLLMProvider.complete()`. The rest of the system is unaffected.

**Prompt versioning.** `prompt_version` is stored on each `daily_digests` record. This enables A/B comparison of prompt changes over time and supports future experimentation workflows.

---

## 14. Observability

The pipeline is designed to be observable through structured logging without requiring external monitoring infrastructure. Each stage emits key operational signals:

- **Ingestion timing** — per-source fetch duration; early indicator of source-level latency or failure trends
- **Token usage** — `token_count` per article after cleaning; informs summarization routing (standard vs. hierarchical) and tracks LLM cost over time
- **Summarization latency** — per-article LLM call duration; flags unexpectedly slow responses
- **Retry metrics** — `retry_count` and `last_retry_at` per article; surfaces systematic summarization failures
- **Source failure tracking** — `failure_count` and `last_error` per source; persisted in the database and visible across runs
- **Pipeline summary** — emitted at run completion: sources attempted/succeeded/failed, articles ingested/summarized/included, digest article count, email delivery status

All logging uses structured output to support future log aggregation without format changes. No external observability service is required at MVP scale.
