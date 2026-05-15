# DailyDigest-AI — Implementation Plan

A Python backend that aggregates AI news from YouTube channels and blog posts, stores them in PostgreSQL, and generates a personalized daily digest via LLM, delivered to your inbox.

---

## Proposed Project Structure

```
DailyDigest-AI/
├── app/
│   ├── __init__.py
│   ├── config.py              # Pydantic Settings (env vars)
│   ├── database.py            # SQLAlchemy engine + session
│   ├── models/
│   │   ├── __init__.py
│   │   ├── mixins.py          # TimestampMixin (created_at, updated_at)
│   │   ├── source.py          # Source model
│   │   ├── article.py         # Article model + ProcessingStatus enum
│   │   └── digest.py          # DailyDigest model
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── base.py            # Abstract BaseIngester
│   │   ├── youtube.py         # YouTube RSS ingester
│   │   └── blog.py            # Blog/RSS ingester (trafilatura fallback)
│   ├── processing/
│   │   ├── __init__.py
│   │   └── cleaner.py         # HTML stripping, transcript normalization, whitespace cleanup, token estimation
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── base.py            # BaseLLMProvider abstract class
│   │   ├── anthropic.py       # AnthropicProvider implementation
│   │   └── openai.py          # OpenAIProvider implementation
│   ├── digest/
│   │   ├── __init__.py
│   │   └── generator.py       # LLM digest generation (per-article summarization + digest assembly)
│   ├── email/
│   │   ├── __init__.py
│   │   └── sender.py          # Email delivery via Resend SDK
│   ├── utils/
│   │   └── __init__.py        # Shared helpers: hashing, markdown, retry, etc.
│   ├── prompts/
│   │   └── user_interests.md  # Plain text, read at runtime — not in env
│   └── runner.py              # Main orchestration entrypoint
├── alembic.ini                # Alembic config — project root (standard layout)
├── migrations/
│   ├── env.py                 # Alembic environment (wired to SQLAlchemy models)
│   └── versions/
│       └── 0001_initial_schema.py  # Initial migration covering all three tables
├── docker/
│   ├── docker-compose.yml     # Minimal PostgreSQL setup
│   └── .env.example           # Example env file for Docker
├── docs/
│   ├── architecture.md        # Conceptual architecture reference
│   ├── implementation.md      # This document — finalized implementation plan
│   └── example_pipeline.md    # Behavioral examples and data transformation reference
├── scripts/
│   └── seed_sources.py        # One-time script to add initial sources
├── tests/                     # Reserved for future tests
├── pyproject.toml             # Updated with all dependencies
├── .env                       # Local env vars (git-ignored)
├── .env.example               # Template env file
├── main.py                    # Entrypoint — run after: alembic upgrade head
└── README.md
```

---

## Database Schema

### Shared `TimestampMixin`
Every table gets `created_at` and `updated_at` via a shared mixin defined in `app/models/mixins.py`, not individually per model. `updated_at` is auto-updated on every write.

---

### `sources` table
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `name` | String | e.g. "OpenAI Blog", "Lex Fridman" |
| `type` | Enum | `youtube` \| `blog` |
| `url` | String | RSS feed URL or blog base URL |
| `is_active` | Boolean | Toggle scraping on/off |
| `last_fetched_at` | DateTime nullable | When last successfully scraped |
| `fetch_interval_minutes` | Integer | Default 1440 (24 hrs) |
| `failure_count` | Integer | Default 0, increments on scrape error |
| `last_error` | Text nullable | Last error message |
| `created_at` | DateTime | Via TimestampMixin |
| `updated_at` | DateTime | Via TimestampMixin, auto-updated |

---

### `articles` table
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `source_id` | UUID FK → sources | |
| `title` | String | |
| `url` | String unique | Original article/video URL |
| `content_hash` | String unique | SHA256 of `cleaned_content` |
| `raw_content` | Text | Exactly what was scraped — never modified |
| `cleaned_content` | Text | After noise removal |
| `summary` | Text nullable | LLM-generated summary, max 300 words — length driven by content richness |
| `summary_model` | String nullable | Which model generated the summary (distinct from `model_used` on `daily_digests`) |
| `token_count` | Integer nullable | Populated after cleaning; useful for cost debugging and batching |
| `processing_status` | Enum | `fetched` → `cleaned` → `summarized` → `included_in_digest` / `failed` |
| `processing_error` | Text nullable | Last error message if status is `failed` |
| `retry_count` | Integer | Default 0; increments each time summarization is retried after a failure |
| `last_retry_at` | DateTime nullable | Timestamp of the last retry attempt |
| `published_at` | DateTime | From feed |
| `scraped_at` | DateTime | When fetched |
| `created_at` | DateTime | Via TimestampMixin |
| `updated_at` | DateTime | Via TimestampMixin, auto-updated |

> [!NOTE]
> `summary` is populated by **Step 1** of the two-step LLM pipeline (see digest generation below). The digest assembler reads `summary`, not `cleaned_content`.

---

### `daily_digests` table
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `digest_date` | Date unique | One digest per day |
| `markdown_content` | Text | Raw LLM output |
| `html_content` | Text | Converted from markdown for email rendering |
| `prompt_version` | String | e.g. `"v1.0"` |
| `model_used` | String | e.g. `"claude-sonnet-4-5"` |
| `article_count` | Integer | How many articles were included |
| `sent_at` | DateTime nullable | When email was sent |
| `created_at` | DateTime | Via TimestampMixin |
| `updated_at` | DateTime | Via TimestampMixin, auto-updated |

> [!NOTE]
> The old `content` column is replaced by `markdown_content` + `html_content`. The initial Alembic migration reflects this — there is no rename, since the schema is being defined fresh.

---

## Component Details

### 1. `app/config.py` — Configuration

Uses `pydantic-settings` to load from `.env`:

- `DATABASE_URL` — PostgreSQL connection string
- `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`
- `RESEND_API_KEY`
- `LLM_PROVIDER` — `"anthropic"` or `"openai"` (selects which provider is instantiated at startup)
- `DIGEST_RECIPIENT_EMAIL`
- `DIGEST_LOOKBACK_HOURS` (default: 24)

**Removed**: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `USER_INTERESTS`.

Includes a Render-specific fix for the injected `postgres://` scheme:

```python
@validator("DATABASE_URL", pre=True)
def fix_postgres_scheme(cls, v: str) -> str:
    return v.replace("postgres://", "postgresql://", 1)
```

---

### 2. `app/models/` — SQLAlchemy Models

- All models inherit from `Base = declarative_base()` and `TimestampMixin`
- `mixins.py` defines `TimestampMixin` with `created_at` and `updated_at`
- `source.py` defines `SourceType` Enum + `Source` model
- `article.py` defines `ProcessingStatus` Enum + `Article` model with FK to `Source`
- `digest.py` defines `DailyDigest` model

---

### 3. `app/ingestion/` — Ingesters

**YouTube (`youtube.py`)**:
- Reads source URL from the `sources` table (`type = youtube`, `is_active = true`)
- Parse YouTube channel RSS: `https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID`
- Use `feedparser` to get video list
- Store title, video URL, description (as `raw_content`), published date
- YouTube transcripts may be significantly larger than typical blog articles — the cleaning and summarization stages account for this

**Blog / Newsletter (`blog.py`)**:
- Reads source URL from the `sources` table (`type = blog`, `is_active = true`)
- Covers blogs and newsletters — both follow the same ingestion flow
- First try RSS feed with `feedparser` — most blogs (OpenAI, Anthropic, Google DeepMind) publish RSS; many newsletters do too
- Fall back to `httpx` + `trafilatura` HTML extraction if no RSS
- Deduplicate by article URL (unique DB constraint)
- On failure: log error, increment `failure_count`, store in `last_error`, continue

MVP ingestion runs synchronously. Async ingestion may be introduced later if source volume or latency warrants it.

---

### 3a. `app/processing/cleaner.py` — Content Cleaning

Responsible for transforming `raw_content` into `cleaned_content`. Runs after ingestion, before summarization.

- Strips HTML tags and decodes entities
- Normalizes whitespace and removes boilerplate (nav, footers, cookie notices)
- Normalizes YouTube transcripts (removes timestamps, fixes transcript artifacts)
- Produces clean, prose-ready text
- Estimates and populates `token_count`

This is a pure transformation step — no LLM calls, no external I/O. Output is written to `article.cleaned_content`. Status advances from `fetched` to `cleaned`.

---

### 4. `app/llm/` — LLM Abstraction Layer

**`base.py`**:
```python
class BaseLLMProvider(ABC):
    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str) -> str: ...
```

**`anthropic.py`** — `AnthropicProvider(BaseLLMProvider)`:
- Wraps the Anthropic Python SDK
- Reads `ANTHROPIC_API_KEY` from config

**`openai.py`** — `OpenAIProvider(BaseLLMProvider)`:
- Wraps the OpenAI Python SDK
- Reads `OPENAI_API_KEY` from config

Config selects which provider is instantiated at startup based on `LLM_PROVIDER`. The digest generator only ever calls `BaseLLMProvider.complete()` — it never imports Anthropic or OpenAI directly. Switching providers requires only a config change.

---

### 5. `app/prompts/user_interests.md`

Plain Markdown/text file read from disk at runtime by the digest generator. Not stored in env or config. Edit this file to update what the LLM is told about the user's interests.

---

### 6. `app/digest/generator.py` — Two-Step LLM Pipeline

Digest generation runs in two discrete LLM steps. No topic grouping — one article = one digest snippet.

---

#### Step 1 — Per-Article Summarization

For each article with `processing_status = cleaned`:
- Determine content length via `token_count`
- Apply the appropriate summarization strategy (see below)
- Store the result in `summary` on the article record
- Record `summary_model`
- Advance `processing_status` to `summarized`

This step has no system prompt and no user interest context. The summary reflects the article, not the reader. Interests enter only in Step 2.

**Standard summarization (blogs, newsletters, short transcripts):**

A single LLM call with the full `cleaned_content`.

```
Write as much as this content deserves. If the key insight
can be captured in 2-3 sentences, do that. If there is
genuinely a lot of interesting substance, write more.
Never pad. Never truncate something interesting just to
keep it short. Maximum 300 words.
```

**Hierarchical summarization (very large content — long YouTube transcripts):**

Long transcripts exceed what a single-pass prompt can handle coherently. Isolated chunk summarization is explicitly avoided because:

- Later chunks may lack context established in earlier sections
- Conversational content has cross-section dependencies (a conclusion may only make sense given a premise from 40 minutes earlier)
- Naive chunking produces summaries that feel disconnected and lose narrative continuity

Instead, content is processed progressively:

1. Split `cleaned_content` into overlapping chunks
2. Summarize the first chunk independently
3. For each subsequent chunk, the LLM receives the current chunk plus context from prior processing — which may include compressed memory, the most recent chunk summary, or a running summary of earlier sections
4. A final pass synthesizes the accumulated summaries into one coherent article summary

This is **not RAG**. No vector database is involved. No retrieval system is used. Chunking is a long-document processing strategy implemented entirely in memory within a single pipeline run.

The goal is to preserve narrative continuity, concept persistence, and evolving discussion context across the full length of the transcript.

---

#### Step 2 — Digest Assembly

For each article with `processing_status = summarized`:
- Read all summaries
- Read `app/prompts/user_interests.md` from disk
- Build one prompt with all summaries and call `llm_provider.complete(system_prompt, user_prompt)`
- Convert Markdown output to HTML
- Save both `markdown_content` and `html_content` to the digest record
- Record `model_used` and `prompt_version`
- Mark all included articles as `processing_status = included_in_digest`

**Step 2 prompt:**
```
System: You are a personal AI research assistant.
        The user's interests: {contents of user_interests.md}

        Rules for the digest:
        - Only include articles genuinely worth the user's attention
        - Target up to 10 high-value articles per digest. On quieter
          days with less relevant content, fewer entries is correct.
          Prioritize signal quality over filling a fixed length.
        - Do not pad. On a quiet news day, 3 good snippets is
          better than 8 mediocre ones
        - Each snippet should contain actual insight and specific
          details, not just a restatement of the headline
        - Format in Markdown with clear section breaks between snippets

User: Here are today's article summaries:

      [Article 1]
        Source: Lex Fridman (YouTube)
        URL: https://...
        Summary: {summary}

      [Article 2]
        Source: Anthropic Blog
        URL: https://...
        Summary: {summary}
      ...
```

> [!NOTE]
> Topic grouping / duplicate merging is explicitly out of scope for MVP. Each article produces exactly one digest snippet. Grouping via embeddings and clustering can be added in a later iteration.

---

### 7. `app/email/sender.py` — Email Delivery via Resend

Uses the `resend` Python SDK (not SMTP). Sends `html_content` from the digest record.

- Subject format: `Your AI Digest — {date}`
- Falls back gracefully if sending fails (logs error, doesn't crash pipeline)
- Email body includes a status footer: `"X sources scraped successfully. Y sources failed: [names]"`

---

### 8. `app/runner.py` — Orchestration

Migrations are **not** run automatically. They are a manual step before running the app:
```
alembic upgrade head
python main.py
```

```python
def run():
    1. Query `sources` table for all records WHERE `is_active = true`
       - Each record defines a source URL, type (youtube / blog), and fetch strategy
       - For each active source:
       - Try to ingest → on failure: increment failure_count,
         store error in last_error, log it, continue to next source
       - Never stop the pipeline because one source failed
    2. For each article with status `fetched`:
       - Clean raw_content → cleaned_content (HTML strip, normalize, token count)
       - Advance status to `cleaned`
    3. For each article with status `cleaned`:
       - Run Step 1 LLM: cleaned_content → summary
         (standard or hierarchical depending on token_count)
       - Advance status to `summarized`
    4. Collect all articles with status `summarized`
    5. Run Step 2 LLM: all summaries → digest markdown (up to 10 high-value articles)
    6. Convert markdown to HTML
    7. Save digest to DB (markdown_content, html_content, model_used, prompt_version)
    8. Send email — include status footer:
       "X sources ingested successfully. Y sources failed: [names]"
    9. Log full pipeline summary
```

---

### 9. `docker/docker-compose.yml` — Minimal PostgreSQL

```yaml
services:
  db:
    image: postgres:16-alpine
    ports: ["5432:5432"]
    env_file: .env
    volumes:
      - postgres_data:/var/lib/postgresql/data
```

---

### 10. `alembic.ini` + `migrations/` — Alembic Setup

`alembic.ini` lives at the project root (standard convention). Alembic is wired to the SQLAlchemy models from the start. The initial migration (`0001_initial_schema.py`) covers all three tables with the full schema defined above.

Migrations are run **manually** before starting the app — never auto-executed by the runner:
```
alembic upgrade head
python main.py
```

---

## Proposed Dependencies

```toml
dependencies = [
    "sqlalchemy>=2.0",
    "psycopg2-binary",       # PostgreSQL driver
    "alembic",               # DB migrations
    "pydantic-settings",     # Config from .env
    "feedparser",            # RSS/Atom feed parsing
    "httpx",                 # HTTP client
    "trafilatura",           # HTML content extraction
    "anthropic",             # Anthropic SDK (Claude)
    "openai",                # OpenAI SDK (optional provider)
    "resend",                # Email delivery
    "markdown",              # Markdown → HTML conversion
    "python-dotenv",
]
```

**Removed**: `schedule` (replaced by Render Cron Job).  
**Removed**: SMTP-related config (replaced by Resend).

---

## Scheduler Strategy

| Environment | Approach |
|---|---|
| Local dev | Run `python main.py` manually |
| Production (Render) | Render Cron Job — `0 7 * * *` (7am UTC daily) |

No in-process scheduler (`schedule` library) — removed entirely.

---

## Render Deployment Plan

- **Service type**: Cron Job
- **Build**: `pip install -e .`
- **Command**: `python main.py`
- **Schedule**: `0 7 * * *`
- **Environment variables**: Set all `.env` values in Render dashboard
- **Database**: Render managed PostgreSQL (free tier)
- **`DATABASE_URL`**: Injected automatically by Render when a PostgreSQL instance is linked; `fix_postgres_scheme` validator corrects the `postgres://` → `postgresql://` prefix automatically

---

## Verification Plan

### Local Testing
1. `docker compose -f docker/docker-compose.yml up -d` — start PostgreSQL
2. Set env vars in `.env`
3. `alembic upgrade head` — apply migrations
4. `python main.py` — runs full pipeline (ingest → summarize → digest → email)
5. Check DB tables via psql or GUI (TablePlus, DBeaver)
6. Verify email received in inbox

### Seeding
- `python scripts/seed_sources.py` — seeds initial source list

### Automated Checks (future)
- Unit-testable ingesters with mock feed data
- LLM provider mock for digest generator tests

---

## Observability

The pipeline emits structured logs at each stage. Key signals to capture:

- **Ingestion timing** — per-source fetch duration; useful for detecting slow or failing sources early
- **Token usage** — `token_count` per article after cleaning; used to route standard vs. hierarchical summarization and to track LLM cost over time
- **Summarization latency** — per-article LLM call duration; flags unexpectedly slow calls
- **Retry metrics** — `retry_count` and `last_retry_at` per article; surfaces systematic summarization failures
- **Source failure tracking** — `failure_count` and `last_error` per source; trends indicate sources that need attention
- **Pipeline summary** — logged at the end of each run: sources attempted/succeeded/failed, articles ingested/summarized/included, digest article count, email delivery status

All logging uses structured output (key-value pairs or JSON) to support future log aggregation without format changes.
