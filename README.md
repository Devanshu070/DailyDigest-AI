# DailyDigest-AI

A personal AI-powered news aggregator that ingests content from YouTube channels and blog RSS feeds, summarizes each article with an LLM, assembles a personalized daily digest, and delivers it to your inbox every morning.

---

## What it does

1. **Ingests** articles from YouTube (via RSS) and blog feeds (HTML scraping)
2. **Cleans** raw content and removes boilerplate
3. **Summarizes** each article independently — content-agnostic, no user context at this stage
4. **Assembles** a personalized digest using your interest profile (`app/prompts/user_interests.md`)
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

## Personalization

Edit `app/prompts/user_interests.md` to describe your interests. This file is the sole input to the digest assembly step — the LLM uses it to decide which articles to include, skip, and how to frame each snippet.

---

## Docs

- [`docs/architecture_final.md`](docs/architecture_final.md) — System architecture diagrams (ER, sequence, class, state machine)
- [`docs/dev_architecture.md`](docs/dev_architecture.md) — Developer reference: modules, pipeline, invariants
- [`docs/example_pipeline.md`](docs/example_pipeline.md) — End-to-end worked example with sample inputs/outputs
- [`docs/data_flow.md`](docs/data_flow.md) — Step-by-step data flow through the pipeline

---

## License

MIT