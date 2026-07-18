"""
runner.py — Main pipeline orchestrator (multi-user).

Execution order:
  1. Determine run mode (scheduled vs manual)
  2. Load all active users from DB
  3. For each user — check if their digest is due:
       scheduled: now >= today's digest_time AND last_scheduled_digest_at < today's digest_time
       manual:    always run
  4. For each due user:
     a. Compute window: [last_scheduled_digest_at → today's digest_time]  (scheduled)
                        [now - 24h              → now               ]    (manual)
     b. For each subscribed source — fetch only the gap using fetched_till watermark
     c. Clean + summarize newly-fetched articles
     d. Collect ALL summarized articles in the window for this user's sources (cache hits)
     e. Assemble personalized digest using user.interests_md
     f. Send email to user.email → update user.last_digest_at (always)
                                  + update user.last_scheduled_digest_at (scheduled only)

Timestamp semantics:
  last_digest_at           — most recent email sent (scheduled OR manual). Read by the frontend.
  last_scheduled_digest_at — most recent SCHEDULED email sent. Read ONLY by the skip guard
                              to prevent double-delivery. Never updated by manual runs.

Run modes:
  python main.py            → scheduled mode (snaps to each user's digest_time)
  python main.py --manual   → manual mode (rolling now-24h → now, runs for all users)
"""

import hashlib
import logging
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.database import get_db
from app.models import (
    Article, ProcessingStatus, Source, SourceType,
    User, UserSourceAlias,
)
from app.utils.helpers import last_scheduled_digest_time
from app.processing.cleaner import clean
from app.ingestion.youtube.ingester import YouTubeIngester
from app.ingestion.blog.ingester import BlogIngester
from app.llm import llm_summarizer, llm_assembler
from app.digest.summarizer import summarize_article
from app.digest.models import ArticleSummaryInput
from app.digest.assembler import generate_digest
from app.email.sender import send_digest

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

from typing import Callable, Optional

def run(
    manual: bool = False,
    target_email: str | None = None,
    on_stage: Optional[Callable[[str, str], None]] = None,
    on_email_ready: Optional[Callable[[str, str], None]] = None,
) -> None:
    """
    Runs the DailyDigest pipeline.

    Args:
        manual: If True — runs for the specified target_email right now with a rolling
                24h window (now-24h → now). Used for on-demand/API-triggered runs.
                If False (default) — scheduled mode: only runs for active users whose
                digest_time has passed today and haven't received a digest yet.
        target_email: For manual runs, the specific user to generate a digest for.
                Defaults to settings.digest_recipient_email.
        on_stage: Optional callback(stage, message) for progress tracking.
        on_email_ready: Optional callback(html, subject) called when email HTML is ready.
    """
    _stage = on_stage or (lambda s, m="": None)

    now = datetime.now(timezone.utc)
    log.info("Pipeline started (mode=%s, now=%s)", "manual" if manual else "scheduled", now.isoformat())

    # Load active users from DB
    with get_db() as db:
        if manual:
            email_to_run = target_email or settings.digest_recipient_email
            log.info("Manual mode: targeting specific user %s", email_to_run)
            users = db.query(User).filter_by(email=email_to_run, is_active=True).all()
        else:
            users = db.query(User).filter_by(is_active=True).all()
            
        db.expunge_all()

    if not users:
        log.warning("No active users found — nothing to do.")
        return

    log.info("Found %d active user(s)", len(users))

    for user in users:
        if manual:
            window_start = now - timedelta(hours=24)
            window_end = now
        else:
            # Skip guard: only check the scheduler's own bookkeeping column.
            # Manual runs do NOT update last_scheduled_digest_at, so they cannot
            # accidentally suppress the next scheduled delivery.
            if user.last_scheduled_digest_at and user.last_scheduled_digest_at >= (now - timedelta(hours=24)):
                log.info(
                    "User %s: already received a scheduled digest %s ago — skipping.",
                    user.email,
                    str(now - user.last_scheduled_digest_at).split(".")[0],
                )
                continue

            window_end = last_scheduled_digest_time(user.digest_time, now)
            window_start = window_end - timedelta(hours=24)

        log.info(
            "--- Running pipeline for %s | window: %s → %s ---",
            user.email, window_start.isoformat(), window_end.isoformat(),
        )

        try:
            _run_for_user(user, window_start, window_end, manual, _stage, on_email_ready)
        except Exception as exc:
            log.error("Pipeline failed for user %s: %s", user.email, exc, exc_info=True)


# ---------------------------------------------------------------------------
# Per-user pipeline
# ---------------------------------------------------------------------------

def _run_for_user(
    user: User,
    window_start: datetime,
    window_end: datetime,
    manual: bool = False,
    on_stage: Callable[[str, str], None] = lambda s, m="": None,
    on_email_ready: Optional[Callable[[str, str], None]] = None,
) -> None:
    """Runs the full ingestion → digest → email pipeline for one user."""

    # ── Step 1: Load user's subscribed sources from DB ──────────────────────
    with get_db() as db:
        source_ids = [
            r[0] for r in db.query(UserSourceAlias.source_id).filter_by(user_id=user.id).all()
        ]

        if not source_ids:
            log.warning("User %s has no subscribed sources — skipping.", user.email)
            on_stage("done", "No sources subscribed")
            if on_email_ready:
                on_email_ready(
                    "<h2>No sources configured 📡</h2>"
                    "<p>You have no sources subscribed yet. "
                    "Go to the <a href='/sources'>Sources</a> page to add your first source, "
                    "then run the pipeline again.</p>",
                    "No sources configured",
                )
            return

        sources = (
            db.query(Source)
            .filter(Source.id.in_(source_ids), Source.is_active == True)  # noqa: E712
            .all()
        )
        db.expunge_all()

    log.info("Loaded %d source(s) for %s", len(sources), user.email)

    # ── Step 2: Ingest each source ──────────────────────────────────────────
    on_stage("fetching_articles", f"Fetching articles from {len(sources)} source(s)…")
    failed_sources: list[tuple[str, str]] = []
    ingested_count = 0

    for source in sources:
        try:
            # Only fetch the portion of the window not yet in the DB
            gap_start = max(window_start, source.fetched_till) \
                if source.fetched_till else window_start

            if gap_start >= window_end:
                log.info("Source '%s' fully cached (fetched_till=%s) — skipping fetch.",
                         source.url, source.fetched_till)
                continue

            log.info("Fetching '%s' [%s → %s]", source.url,
                     gap_start.isoformat(), window_end.isoformat())

            if source.type == SourceType.youtube:
                ingester = YouTubeIngester(run_at=window_end, window_start=gap_start)
            else:
                ingester = BlogIngester(run_at=window_end, window_start=gap_start)

            entries = ingester.fetch(source.url)
            articles_data = ingester.parse(entries)

            new_count = 0
            with get_db() as db:
                for article_data in articles_data:

                    db.add(Article(
                        source_id=source.id,
                        title=article_data["title"],
                        url=article_data["url"],
                        raw_content=article_data["raw_content"],
                        published_at=article_data["published_at"],
                        scraped_at=datetime.now(timezone.utc),
                        processing_status=ProcessingStatus.fetched,
                    ))
                    new_count += 1

                # Advance the watermark
                db.query(Source).filter_by(id=source.id).update({
                    "last_fetched_at": datetime.now(timezone.utc),
                    "fetched_till": window_end,
                })

            ingested_count += new_count
            log.info("Ingested %d new article(s) from '%s'", new_count, source.url)

        except Exception as exc:
            log.error("Ingestion failed for source '%s': %s", source.url, exc)
            failed_sources.append((source.url, str(exc)))
            with get_db() as db:
                db.query(Source).filter_by(id=source.id).update({
                    "failure_count": Source.failure_count + 1,
                    "last_error": str(exc),
                })

    log.info("Ingestion complete: %d new articles, %d/%d sources ok",
             ingested_count, len(sources) - len(failed_sources), len(sources))

    # ── Step 3: Clean newly-fetched articles ────────────────────────────────
    on_stage("cleaning", f"Cleaning & deduplicating {ingested_count} new article(s)…")
    cleaned_count = 0
    with get_db() as db:
        fetched_articles = (
            db.query(Article)
            .filter(
                Article.processing_status == ProcessingStatus.fetched,
                Article.source_id.in_(source_ids),
                Article.published_at >= window_start,
                Article.published_at < window_end,
            )
            .all()
        )
        db.expunge_all()

    for article in fetched_articles:
        try:
            source_type = "youtube" if _is_youtube(article.url) else "blog"
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

        except Exception as exc:
            log.error("Cleaning failed for '%s': %s", article.title, exc)
            with get_db() as db:
                db.query(Article).filter_by(id=article.id).update({
                    "processing_status": ProcessingStatus.failed,
                    "processing_error": str(exc),
                })

    log.info("Cleaning complete: %d/%d articles cleaned", cleaned_count, len(fetched_articles))

    # ── Step 4: Summarize cleaned articles from this user's sources ─────────
    on_stage("summarizing", "Summarizing articles with AI…")
    with get_db() as db:
        cleaned_articles = (
            db.query(Article)
            .filter(
                Article.processing_status == ProcessingStatus.cleaned,
                Article.source_id.in_(source_ids),
                Article.published_at >= window_start,
                Article.published_at < window_end,
            )
            .all()
        )
        db.expunge_all()

    newly_summarized = 0
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
            newly_summarized += 1

        except Exception as exc:
            log.error("Summarization failed for '%s': %s", article.title, exc)
            with get_db() as db:
                db.query(Article).filter_by(id=article.id).update({
                    "processing_status": ProcessingStatus.failed,
                    "processing_error": str(exc),
                    "retry_count": Article.retry_count + 1,
                    "last_retry_at": datetime.now(timezone.utc),
                })

    log.info("Summarization complete: %d/%d articles summarized",
             newly_summarized, len(cleaned_articles))

    on_stage("assembling_digest", "Collecting summarized articles from window…")
    # ── Collect ALL summarized articles in the window (cache hits included) ─
    with get_db() as db:
        window_articles = (
            db.query(Article)
            .filter(
                Article.processing_status == ProcessingStatus.summarized,
                Article.source_id.in_(source_ids),
                Article.published_at >= window_start,
                Article.published_at < window_end,
            )
            .all()
        )
        db.expunge_all()

    all_inputs: list[ArticleSummaryInput] = []
    all_summaries: list[str] = []
    for article in window_articles:
        if article.summary:
            all_inputs.append(ArticleSummaryInput(
                title=article.title,
                url=article.url,
                source_name=_source_label(article),
                cleaned_content=article.cleaned_content or "",
                token_count=article.token_count or 0,
            ))
            all_summaries.append(article.summary)


    if not all_summaries:
        log.info("No articles in window for user %s — sending quiet-day email.", user.email)
        on_stage("sending_email", "Sending quiet-day email…")
        quiet_html = (
            "<h2>Nothing new today 🤫</h2>"
            "<p>None of your subscribed sources published anything in the last 24 hours. "
            "Check back tomorrow!</p>"
        )
        status_footer = _build_status_footer(sources, failed_sources)
        if on_email_ready:
            on_email_ready(quiet_html, f"Quiet Day — {window_end.date()}")
        sent = send_digest(
            html_content=quiet_html,
            digest_date=window_end.date(),
            status_footer=status_footer,
            recipient_email=user.email,
        )
        if sent:
            update_fields: dict = {"last_digest_at": window_end}
            if not manual:
                # Only update the scheduler's bookkeeping column on scheduled runs
                update_fields["last_scheduled_digest_at"] = window_end
            with get_db() as db:
                db.query(User).filter_by(id=user.id).update(update_fields)
            log.info(
                "Quiet-day email sent to %s — last_digest_at updated%s.",
                user.email,
                ", last_scheduled_digest_at updated" if not manual else "",
            )
        return

    log.info("Assembling digest from %d article(s) for %s", len(all_summaries), user.email)

    # ── Step 5: Assemble personalized digest ────────────────────────────────
    on_stage("assembling_digest", f"Assembling personalized digest from {len(all_summaries)} article(s)…")
    try:
        digest_result = generate_digest(
            all_inputs,
            all_summaries,
            llm_assembler,
            interests_md=user.interests_md or None,
        )
        log.info("Digest assembled: %d articles (model=%s)",
                 digest_result.article_count, digest_result.model_used)

    except Exception as exc:
        log.error("Digest assembly failed for user %s: %s", user.email, exc)
        raise  # let _run_pipeline_background catch it and call _run_state.fail()

    # ── Step 6: Send email → update last_digest_at ──────────────────────────
    on_stage("sending_email", "Sending email…")
    if on_email_ready:
        on_email_ready(digest_result.html_content, f"Your DailyDigest for {window_end.date()}")
    status_footer = _build_status_footer(sources, failed_sources)
    sent = send_digest(
        html_content=digest_result.html_content,
        digest_date=window_end.date(),
        status_footer=status_footer,
        recipient_email=user.email,
    )

    if sent:
        update_fields: dict = {"last_digest_at": window_end}
        if not manual:
            # Only update the scheduler's bookkeeping column on scheduled runs
            update_fields["last_scheduled_digest_at"] = window_end
        with get_db() as db:
            db.query(User).filter_by(id=user.id).update(update_fields)
        log.info(
            "Digest sent to %s — last_digest_at updated%s.",
            user.email,
            ", last_scheduled_digest_at updated" if not manual else "",
        )

    log.info(
        "Pipeline complete for %s | %d sources ok / %d failed | "
        "%d ingested / %d cleaned / %d summarized / %d in digest",
        user.email,
        len(sources) - len(failed_sources), len(failed_sources),
        ingested_count, cleaned_count, newly_summarized, digest_result.article_count,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_youtube(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


def _source_label(article: Article) -> str:
    """Human-readable source label for the digest prompt."""
    if _is_youtube(article.url):
        return f"{article.title} (YouTube)"
    return article.title


def _build_status_footer(sources: list, failed_sources: list[tuple]) -> str:
    ok = len(sources) - len(failed_sources)
    if failed_sources:
        names = ", ".join(n for n, _ in failed_sources)
        return f"{ok} sources ingested successfully. {len(failed_sources)} failed: {names}"
    return f"{ok} sources ingested successfully."
    