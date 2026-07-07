# DailyDigest-AI

A personal AI-powered news aggregator that ingests content from YouTube channels and blog RSS feeds, summarizes each article with an LLM, assembles a personalized daily digest, and delivers it to your inbox every morning.

---

## What it does

1. **Ingests** articles from YouTube (via RSS) and blog feeds (HTML scraping)
2. **Cleans** raw content and removes boilerplate
3. **Summarizes** each article independently using an LLM — content-agnostic, no user context at this stage
4. **Assembles** a personalized digest: a second, larger LLM reads all the per-article summaries alongside your interest profile (`app/prompts/user_interests.md`) and acts as a personal research assistant — filtering out low-signal noise, merging duplicate coverage, and writing a curated briefing tailored specifically to you
5. **Emails** the digest as a formatted HTML email via [Resend](https://resend.com)

Designed to run on a daily cron schedule (e.g. Render).

---

## Stack

| Layer       | Technology                        |
|-------------|-----------------------------------|
| Language    | Python 3.12+                      |
| Database    | PostgreSQL via SQLAlchemy + Alembic |
| LLM         | Groq (Llama 4 Scout + GPT-OSS, swappable) |
| Email       | Resend                            |
| Package mgr | [uv](https://docs.astral.sh/uv/)  |
| Local DB    | Docker Compose                    |

---

## Project structure

```
app/
  ingestion/      # YouTube + blog ingesters
  processing/     # Content cleaning + token estimation
  digest/         # Step 1 summarization + Step 2 digest assembly
  email/          # Markdown → HTML + Resend delivery
  llm/            # BaseLLMProvider + Anthropic/OpenAI implementations
  models/         # SQLAlchemy ORM models
  prompts/        # user_interests.md — edit this to personalize your digest
  utils/          # Shared helpers
docker/           # PostgreSQL docker-compose
scripts/          # One-off operational scripts
migrations/       # Alembic migrations
docs/             # Architecture + pipeline documentation
main.py           # Entrypoint
```

---

## Getting started

### 1. Clone and install

```bash
git clone https://github.com/Devanshu070/DailyDigest-AI.git
cd DailyDigest-AI
uv sync
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your API keys and database URL
```

### 3. Start the database

```bash
docker compose -f docker/docker-compose.yml up -d
```

### 4. Run migrations

```bash
uv run alembic upgrade head
```

### 5. Seed sources

```bash
uv run python scripts/seed_sources.py
```

### 6. Run the pipeline

```bash
uv run python main.py
```

---

## Automation (GitHub Actions)

The pipeline runs automatically via GitHub Actions every day at **06:00 UTC (11:30 AM IST)**.

### Changing the delivery time
Edit the cron expression in [`.github/workflows/daily_digest.yml`](.github/workflows/daily_digest.yml):
```yaml
schedule:
  - cron: "0 6 * * *"  # ← change this line
```
Use [crontab.guru](https://crontab.guru) to build your expression. Times are always in UTC.

### Required GitHub Secrets
Go to **Settings → Secrets and variables → Actions** in your GitHub repo and add:

| Secret | Description |
|--------|-------------|
| `DATABASE_URL` | Your hosted PostgreSQL URL (Supabase / Neon / Railway) |
| `GROQ_API_KEY` | Your Groq API key |
| `RESEND_API_KEY` | Your Resend API key |
| `DIGEST_RECIPIENT_EMAIL` | The email address to deliver the digest to |

> **Note:** The `DATABASE_URL` must point to a cloud-hosted PostgreSQL instance, not `localhost`. GitHub Actions runners cannot reach your local Docker database.

### Manual runs
You can also trigger the pipeline on-demand from the **Actions** tab on GitHub without waiting for the scheduled time.

---

## Personalization

There are two files you should edit to make the digest your own:

### 1. `scripts/seed_sources.py` — Your content sources
This script populates the database with the YouTube channels and blog RSS feeds you want to follow. Edit the list of sources at the top of the file, then re-run it:
```bash
uv run python scripts/seed_sources.py
```

### 2. `app/prompts/user_interests.md` — Your interest profile
This is the most important file. It is the sole input to the digest assembly step — the LLM uses it to decide which articles to include, which to skip, how to merge overlapping coverage, and how to frame each snippet. Write it as if you are briefing a personal research assistant.

---

## Docs

- [`docs/architecture_final.md`](docs/architecture_final.md) — System architecture diagrams (ER, sequence, class, state machine)
- [`docs/dev_architecture.md`](docs/dev_architecture.md) — Developer reference: modules, pipeline, invariants
- [`docs/example_pipeline.md`](docs/example_pipeline.md) — End-to-end worked example with sample inputs/outputs
- [`docs/data_flow.md`](docs/data_flow.md) — Step-by-step data flow through the pipeline

---

## License

MIT