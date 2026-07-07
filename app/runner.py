"""
runner.py — Main pipeline orchestrator.

Execution order:
  1. Load all active sources from DB
  2. Ingest each source (YouTube / Blog) → store raw articles
  3. Clean each fetched article → store cleaned_content + token_count
  4. Summarize each cleaned article via LLM → store summary
  5. Assemble digest from all summaries → select top articles (max 10) → store markdown
  6. Convert markdown digest → HTML
  7. Send digest via email
  8. Log full pipeline summary

Run manually (after `alembic upgrade head`):
  python main.py
"""

import hashlib
import logging
from datetime import date, datetime, timezone

from app.database import get_db
from app.models import Article, DailyDigest, ProcessingStatus, Source, SourceType
from app.processing.cleaner import clean
from app.ingestion.youtube.ingester import YouTubeIngester
from app.ingestion.blog.ingester import BlogIngester
from app.llm import llm_summarizer, llm_assembler
from app.digest.summarizer import summarize_article
from app.digest.models import ArticleSummaryInput
from app.digest.assembler import generate_digest
from app.email.sender import send_digest

log = logging.getLogger(__name__)


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
    with get_db() as db:
        sources = db.query(Source).filter_by(is_active=True).all()
        # Detach from session so we can use source objects after the block
        db.expunge_all()

    log.info("Loaded %d active sources", len(sources))

    # ----------------------------------------------------------
    # Step 2 — Ingest each source → persist raw articles to DB
    # ----------------------------------------------------------
    failed_sources = []   # (source_name, error_message)
    ingested_count = 0

    for source in sources:
        try:
            if source.type == SourceType.youtube:
                ingester = YouTubeIngester(run_at=run_at)
            else:
                ingester = BlogIngester(run_at=run_at)

            entries = ingester.fetch(source.url)
            articles = ingester.parse(entries)

            new_count = 0
            with get_db() as db:
                for article_data in articles:
                    # Deduplicate by URL — skip if already in DB
                    exists = db.query(Article).filter_by(url=article_data["url"]).first()
                    if exists:
                        continue

                    db.add(Article(
                        source_id=source.id,
                        title=article_data["title"],
                        url=article_data["url"],
                        raw_content=article_data["raw_content"],
                        published_at=article_data["published_at"],
                        scraped_at=run_at,
                        processing_status=ProcessingStatus.fetched,
                    ))
                    new_count += 1

                # Update last_fetched_at on the source
                db.query(Source).filter_by(id=source.id).update(
                    {"last_fetched_at": run_at}
                )

            ingested_count += new_count
            log.info("Ingested %d new articles from %s", new_count, source.name)

        except Exception as exc:
            log.error("Ingestion failed for source '%s': %s", source.name, exc)
            failed_sources.append((source.name, str(exc)))

            with get_db() as db:
                db.query(Source).filter_by(id=source.id).update({
                    "failure_count": Source.failure_count + 1,
                    "last_error": str(exc),
                })

    log.info(
        "Ingestion complete: %d new articles from %d/%d sources (%d failed)",
        ingested_count,
        len(sources) - len(failed_sources),
        len(sources),
        len(failed_sources),
    )

    # ----------------------------------------------------------
    # Step 3 — Clean each fetched article
    # ----------------------------------------------------------
    cleaned_count = 0

    with get_db() as db:
        fetched_articles = (
            db.query(Article)
            .filter_by(processing_status=ProcessingStatus.fetched)
            .all()
        )
        db.expunge_all()

    for article in fetched_articles:
        try:
            source_type = "youtube" if article.source_id and _is_youtube(article.url) else "blog"
            cleaned_content, token_count = clean(article.raw_content, source_type=source_type)
            content_hash = hashlib.sha256(cleaned_content.encode()).hexdigest()

            with get_db() as db:
                db.query(Article).filter_by(id=article.id).update({
                    "cleaned_content": cleaned_content,
                    "token_count": token_count,
                    "content_hash": content_hash,
                    "processing_status": ProcessingStatus.cleaned,
                })

            cleaned_count += 1
            log.debug("Cleaned '%s' → %d chars, ~%d tokens", article.title, len(cleaned_content), token_count)

        except Exception as exc:
            log.error("Cleaning failed for '%s': %s", article.title, exc)
            with get_db() as db:
                db.query(Article).filter_by(id=article.id).update({
                    "processing_status": ProcessingStatus.failed,
                    "processing_error": str(exc),
                })

    log.info("Cleaning complete: %d/%d articles cleaned", cleaned_count, len(fetched_articles))

    # ----------------------------------------------------------
    # Step 4 — Summarize each cleaned article (LLM Step 1)
    # ----------------------------------------------------------
    summary_inputs: list[ArticleSummaryInput] = []
    summaries: list[str] = []

    with get_db() as db:
        cleaned_articles = (
            db.query(Article)
            .filter_by(processing_status=ProcessingStatus.cleaned)
            .all()
        )
        db.expunge_all()

    for article in cleaned_articles:
        try:
            inp = ArticleSummaryInput(
                title=article.title,
                url=article.url,
                source_name=_source_label(article),
                cleaned_content=article.cleaned_content,
                token_count=article.token_count or 0,
            )
            summary = summarize_article(inp, llm_summarizer)

            with get_db() as db:
                db.query(Article).filter_by(id=article.id).update({
                    "summary": summary,
                    "summary_model": llm_summarizer.model,
                    "processing_status": ProcessingStatus.summarized,
                })

            summary_inputs.append(inp)
            summaries.append(summary)
            log.debug("Summarized '%s' → %d chars", article.title, len(summary))

        except Exception as exc:
            log.error("Summarization failed for '%s': %s", article.title, exc)
            with get_db() as db:
                db.query(Article).filter_by(id=article.id).update({
                    "processing_status": ProcessingStatus.failed,
                    "processing_error": str(exc),
                    "retry_count": Article.retry_count + 1,
                    "last_retry_at": run_at,
                })

    log.info("Summarization complete: %d/%d articles summarized", len(summaries), len(cleaned_articles))

    if not summaries:
        log.warning("No summaries produced — skipping digest assembly and email.")
        return

    # ----------------------------------------------------------
    # Step 5 + 6 — Assemble digest (LLM Step 2) + convert to HTML
    # ----------------------------------------------------------
    try:
        digest_result = generate_digest(summary_inputs, summaries, llm_assembler)

        with get_db() as db:
            digest = DailyDigest(
                digest_date=date.today(),
                markdown_content=digest_result.markdown_content,
                html_content=digest_result.html_content,
                prompt_version=digest_result.prompt_version,
                model_used=digest_result.model_used,
                article_count=digest_result.article_count,
            )
            db.add(digest)

            # Mark all summarized articles as included in this digest
            db.query(Article).filter(
                Article.processing_status == ProcessingStatus.summarized
            ).update({"processing_status": ProcessingStatus.included_in_digest})

        log.info(
            "Digest assembled: %d articles included (model=%s)",
            digest_result.article_count,
            digest_result.model_used,
        )

    except Exception as exc:
        log.error("Digest assembly failed: %s", exc)
        return

    # ----------------------------------------------------------
    # Step 7 — Send email
    # ----------------------------------------------------------
    status_footer = _build_status_footer(sources, failed_sources)
    sent = send_digest(
        html_content=digest_result.html_content,
        digest_date=date.today(),
        status_footer=status_footer,
    )

    if sent:
        with get_db() as db:
            db.query(DailyDigest).filter_by(
                digest_date=date.today()
            ).update({"sent_at": datetime.now(timezone.utc)})

    # ----------------------------------------------------------
    # Step 8 — Pipeline summary log
    # ----------------------------------------------------------
    _log_summary(
        sources=sources,
        failed_sources=failed_sources,
        ingested=ingested_count,
        cleaned=cleaned_count,
        summarized=len(summaries),
        digest_articles=digest_result.article_count,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_youtube(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


def _source_label(article: Article) -> str:
    """Returns a human-readable source label for the digest prompt."""
    if _is_youtube(article.url):
        return f"{article.title} (YouTube)"
    return article.title


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
    ingested: int,
    cleaned: int,
    summarized: int,
    digest_articles: int,
) -> None:
    """Logs a structured end-of-run pipeline summary."""
    log.info(
        "Pipeline complete | sources: %d ok / %d failed | "
        "articles: %d ingested / %d cleaned / %d summarized / %d in digest",
        len(sources) - len(failed_sources),
        len(failed_sources),
        ingested,
        cleaned,
        summarized,
        digest_articles,
    )
