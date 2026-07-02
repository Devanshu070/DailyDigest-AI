"""
runner.py — Main pipeline orchestrator.

Execution order:
  1. Load all active sources from DB
  2. Ingest each source (YouTube / Blog) → store raw articles
  3. Clean each fetched article → store cleaned_content + token_count
  4. Summarize each cleaned article → store summary
  5. Assemble digest from all summaries → select & sort top N articles (max 10) → store markdown + html
  6. Send digest via email
  7. Log full pipeline summary

Run manually (after `alembic upgrade head`):
  python main.py
"""

import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)


# TODO: Import DB session + models (app/database.py, app/models/) once built
# TODO: Import LLM layer (app/llm/) once built — feat/llm-summarization
# TODO: Import digest summarizer + assembler (app/digest/) once built — feat/llm-summarization
# TODO: Import email sender (app/email/sender.py) once built

from app.processing.cleaner import clean
from app.ingestion.youtube.ingester import YouTubeIngester
from app.ingestion.blog.ingester import BlogIngester


def run() -> None:
    """
    Runs the full DailyDigest pipeline end to end.

    All steps are fault-tolerant:
      - A single source failing never stops the pipeline.
      - A single article failing summarization is skipped, not fatal.
      - Email failure is logged but does not raise.
    """
    run_at = datetime.now(timezone.utc)
    log.info("Pipeline started at %s", run_at.isoformat())

    # ----------------------------------------------------------
    # Step 1 — Load active sources from DB
    # ----------------------------------------------------------
    # TODO: Step 1 — replace stub with DB query: Source.filter_by(is_active=True)
    sources = []  # stub — will be populated from DB
    log.info("Loaded %d active sources", len(sources))

    # ----------------------------------------------------------
    # Step 2 — Ingest each source
    # ----------------------------------------------------------
    ingested_articles = []   # list of raw ArticleData dicts
    failed_sources = []      # (source_name, error_message)

    for source in sources:
        try:
            if source.type == "youtube":   # TODO: Step 2 — use SourceType enum; source fields come from DB record
                ingester = YouTubeIngester(run_at=run_at)
            else:
                ingester = BlogIngester(run_at=run_at)

            entries = ingester.fetch(source.url)
            articles = ingester.parse(entries)

            # TODO: Step 2 — deduplicate by URL against DB before appending
            ingested_articles.extend(articles)

            # TODO: Step 2 — update source.last_fetched_at in DB
            log.info("Ingested %d articles from %s", len(articles), source.name)

        except Exception as exc:
            log.error("Ingestion failed for source '%s': %s", source.name, exc)
            failed_sources.append((source.name, str(exc)))

            # TODO: Step 2 — increment source.failure_count and store source.last_error in DB

    log.info(
        "Ingestion complete: %d articles from %d/%d sources (%d failed)",
        len(ingested_articles),
        len(sources) - len(failed_sources),
        len(sources),
        len(failed_sources),
    )

    # ----------------------------------------------------------
    # Step 3 — Clean each fetched article
    # ----------------------------------------------------------
    # TODO: Step 3 — query DB for articles WHERE processing_status = fetched; write cleaned_content + token_count back to DB
    cleaned_articles = []   # will hold (article_db_record, cleaned_content, token_count)

    for article in ingested_articles:
        try:
            source_type = "youtube" if "youtube.com" in article["url"] else "blog"
            cleaned_content, token_count = clean(article["raw_content"], source_type=source_type)

            cleaned_articles.append({
                "title":           article["title"],
                "url":             article["url"],
                "source_name":     article.get("source_name", "Unknown"),
                "cleaned_content": cleaned_content,
                "token_count":     token_count,
            })
            log.debug("Cleaned '%s' → %d chars, ~%d tokens", article["title"], len(cleaned_content), token_count)

        except Exception as exc:
            log.error("Cleaning failed for '%s': %s", article.get("title"), exc)

    log.info("Cleaning complete: %d/%d articles cleaned", len(cleaned_articles), len(ingested_articles))

    # ----------------------------------------------------------
    # Step 4 — Summarize each cleaned article (Step 1 LLM)
    # ----------------------------------------------------------
    # TODO: Step 4 — call summarize_article() per article via LLM; persist summary + model to DB
    summary_inputs: list = []   # stub
    summaries: list = []        # stub

    log.info("[STUB] Summarization not yet implemented — skipping.")

    # ----------------------------------------------------------
    # Step 5 + 6 — Assemble digest (Step 2 LLM) + convert to HTML
    # ----------------------------------------------------------
    # TODO: Step 5 — call generate_digest() to select & sort top 10 articles; persist digest to DB
    # TODO: Step 6 — convert digest markdown to HTML
    log.info("[STUB] Digest assembly not yet implemented — skipping.")

    # ----------------------------------------------------------
    # Step 7 — Send email
    # ----------------------------------------------------------
    # TODO: Step 7 — call send_digest() with HTML content + subject + status footer; update digest.sent_at in DB

    # ----------------------------------------------------------
    # Step 8 — Pipeline summary log
    # ----------------------------------------------------------
    _log_summary(
        sources=sources,
        failed_sources=failed_sources,
        ingested=ingested_articles,
        cleaned=cleaned_articles,
        summarized=summaries,
        digest_articles=0,  # TODO: replace with digest.article_count once Step 5+6 are implemented
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_status_footer(sources: list, failed_sources: list[tuple]) -> str:
    """Builds the status footer included at the bottom of every digest email."""
    ok_count = len(sources) - len(failed_sources)
    if failed_sources:
        failed_names = ", ".join(name for name, _ in failed_sources)
        return f"{ok_count} sources ingested successfully. {len(failed_sources)} failed: {failed_names}"
    return f"{ok_count} sources ingested successfully."


def _log_summary(
    sources: list,
    failed_sources: list[tuple],
    ingested: list,
    cleaned: list,
    summarized: list,
    digest_articles: int,
) -> None:
    """Logs a structured end-of-run pipeline summary."""
    log.info(
        "Pipeline complete | sources: %d ok / %d failed | "
        "articles: %d ingested / %d cleaned / %d summarized / %d in digest",
        len(sources) - len(failed_sources),
        len(failed_sources),
        len(ingested),
        len(cleaned),
        len(summarized),
        digest_articles,
    )
