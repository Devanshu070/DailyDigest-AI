# DailyDigest-AI

A multi-user AI-powered news aggregator that ingests content from YouTube channels and blog RSS feeds, summarizes each article with an LLM, assembles personalized daily digests, and delivers them to your subscribers' inboxes every morning.

---

## What it does

1. **Ingests** articles from YouTube (via RSS) and blog feeds (HTML scraping)
2. **Cleans** raw content and removes boilerplate
3. **Summarizes** each article independently using an LLM — content-agnostic, no user context at this stage
4. **Assembles** a personalized digest for each user: a second, larger LLM reads all the per-article summaries alongside their interest profile and acts as a personal research assistant — filtering out low-signal noise, merging duplicate coverage, and writing a curated briefing tailored specifically to them
5. **Emails** the digest as a formatted HTML email via Gmail SMTP

Designed to run on a recurring cron schedule, it automatically manages rolling 24-hour ingestion windows for each subscriber.

---

## Stack

| Layer       | Technology                        |
|-------------|-----------------------------------|
| Language    | Python 3.12+ / Node.js 18+        |
| Frontend    | Next.js (App Router), React       |
| Database    | PostgreSQL via SQLAlchemy + Alembic |
| LLM         | Groq (Llama 4 Scout + GPT-OSS, swappable) |
| Email       | Gmail SMTP                        |
| Package mgr | [uv](https://docs.astral.sh/uv/)  |
| Local DB    | Docker Compose                    |

---

## Project structure

```
app/              # FastAPI backend & pipeline logic
  ingestion/      # YouTube + blog ingesters
  processing/     # Content cleaning + token estimation
  digest/         # Step 1 summarization + Step 2 digest assembly
  email/          # Markdown → HTML + Gmail SMTP delivery
  llm/            # BaseLLMProvider + Anthropic/OpenAI implementations
  models/         # SQLAlchemy ORM models
  prompts/        # user_interests.md — edit this to personalize your digest
  utils/          # Shared helpers
frontend/         # Next.js web application (Dashboard, Pipeline, Sources, Articles)
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

### 6. Seed user profile

```bash
uv run python scripts/seed_user.py
```

### 7. Run the pipeline

```bash
# Scheduled mode (sends email & updates scheduled timestamp):
uv run python main.py

# Manual mode (generates digest, updates last_digest_at, skips email delivery):
uv run python main.py --manual --email your@email.com
```

### 8. Web App & Pipeline Monitoring

Run the Next.js frontend to manage sources, interests, and trigger pipeline runs via UI:

```bash
cd frontend
npm install
npm run dev
```

- **Pipeline Page**: Triggers on-demand runs with live progress step tracking and inline HTML email previews.
- **State Rehydration**: If you navigate away to Dashboard or Sources while a pipeline is running or completed, returning to the Pipeline page automatically restores the active progress, email preview, and polling status without triggering duplicate runs.

---

## Automation (GitHub Actions)

The pipeline runs automatically via GitHub Actions **every 8 hours**. During each run, it checks the `users` table and processes a digest for anyone whose personal `digest_time` has recently passed.

### Changing the action frequency
By default it runs every 8 hours (`0 */8 * * *`). If you only have users in a specific timezone, you can adjust this frequency by editing [`.github/workflows/daily_digest.yml`](.github/workflows/daily_digest.yml):
```yaml
schedule:
  - cron: "0 */8 * * *"  # ← change this line
```
Use [crontab.guru](https://crontab.guru) to build your expression. Times are always in UTC.

### Required GitHub Secrets
Go to **Settings → Secrets and variables → Actions** in your GitHub repo and add:

| Secret | Description |
|--------|-------------|
| `DATABASE_URL` | Your hosted PostgreSQL URL (Supabase / Neon / Railway) |
| `GROQ_API_KEY` | Your Groq API key |
| `GMAIL_SENDER` | Your sender Gmail address |
| `GMAIL_APP_PASSWORD` | Your 16-character Gmail App Password |
| `DIGEST_RECIPIENT_EMAIL` | The email address to deliver the digest to |

> **Note:** The `DATABASE_URL` must point to a cloud-hosted PostgreSQL instance, not `localhost`. GitHub Actions runners cannot reach your local Docker database.

### Manual runs
You can also trigger the pipeline on-demand from the **Actions** tab on GitHub without waiting for the scheduled time.

---

## Personalization & Multi-User

DailyDigest-AI is now fully database-driven. To manage personalization, you add profiles to the `users` table:

### 1. `scripts/seed_user.py` — Create subscribers
This script makes it incredibly easy to bootstrap your database user profile from your `.env` and `user_interests.md` files, and automatically subscribes you to all active sources.
```bash
uv run python scripts/seed_user.py --email user@example.com
```

### 2. `users.interests_md` — Interest profile
This database column is the sole input to the digest assembly step — the LLM uses it to decide which articles to include, which to skip, how to merge overlapping coverage, and how to frame each snippet. Write it as if you are briefing a personal research assistant.

*(Note: If a user's `interests_md` is empty, the system falls back to the static `app/prompts/user_interests.md` file).*

---

## Docs

- [`docs/architecture_final.md`](docs/architecture_final.md) — System architecture diagrams (ER, sequence, class, state machine)
- [`docs/dev_architecture.md`](docs/dev_architecture.md) — Developer reference: modules, pipeline, invariants
- [`docs/example_pipeline.md`](docs/example_pipeline.md) — End-to-end worked example with sample inputs/outputs
- [`docs/data_flow.md`](docs/data_flow.md) — Step-by-step data flow through the pipeline

---

## License

MIT