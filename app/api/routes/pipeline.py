"""
app/api/routes/pipeline.py — On-demand pipeline trigger + run-state endpoint.

POST /api/v1/pipeline/run          → Kick off the full pipeline in a background thread
GET  /api/v1/pipeline/run-state    → Poll current run progress and last email preview
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status

from app.schemas import PipelineRunResponse

log = logging.getLogger(__name__)
router = APIRouter(prefix="/pipeline", tags=["Pipeline"])

# ── Run-state store (in-memory, single-server) ───────────────────────────────

class RunState:
    """Thread-safe container for the most recent pipeline run's status."""

    STAGES = [
        "idle",
        "fetching_articles",
        "cleaning",
        "summarizing",
        "assembling_digest",
        "generating_digest",
        "sending_email",
        "done",
        "error",
    ]

    STAGE_LABELS = {
        "idle":              "Idle",
        "fetching_articles": "Fetching articles from sources…",
        "cleaning":          "Cleaning & deduplicating articles…",
        "summarizing":       "Summarizing with AI…",
        "assembling_digest": "Assembling personalized digest…",
        "generating_digest": "Generating digest (email skipped for manual run)…",
        "sending_email":     "Sending email…",
        "done":              "Done!",
        "error":             "Error",
    }

    def __init__(self):
        self._lock = threading.Lock()
        self.stage   = "idle"
        self.message = ""
        self.email_html: Optional[str] = None   # last generated HTML
        self.email_subject: Optional[str] = None
        self.started_at: Optional[datetime] = None
        self.finished_at: Optional[datetime] = None
        self.error: Optional[str] = None

    def start(self):
        with self._lock:
            self.stage = "fetching_articles"
            self.message = self.STAGE_LABELS["fetching_articles"]
            self.email_html = None
            self.email_subject = None
            self.started_at = datetime.now(timezone.utc)
            self.finished_at = None
            self.error = None

    def advance(self, stage: str, message: str = ""):
        with self._lock:
            self.stage   = stage
            self.message = message or self.STAGE_LABELS.get(stage, stage)

    def finish(self, html: Optional[str] = None, subject: Optional[str] = None):
        with self._lock:
            self.stage       = "done"
            self.message     = self.STAGE_LABELS["done"]
            self.email_html  = html
            self.email_subject = subject
            self.finished_at = datetime.now(timezone.utc)

    def fail(self, error: str):
        with self._lock:
            self.stage       = "error"
            self.message     = error
            self.error       = error
            self.finished_at = datetime.now(timezone.utc)

    def snapshot(self) -> dict:
        with self._lock:
            stage_index = self.STAGES.index(self.stage) if self.stage in self.STAGES else 0
            # Progress 0-100: done=100, error=100, others proportional
            if self.stage in ("done", "error"):
                pct = 100
            elif self.stage == "idle":
                pct = 0
            else:
                runnable = [s for s in self.STAGES if s not in ("idle", "done", "error")]
                idx = runnable.index(self.stage) if self.stage in runnable else 0
                pct = int(((idx + 1) / len(runnable)) * 90)

            return {
                "stage":        self.stage,
                "label":        self.message,
                "progress_pct": pct,
                "is_running":   self.stage not in ("idle", "done", "error"),
                "email_html":   self.email_html,
                "email_subject": self.email_subject,
                "started_at":   self.started_at.isoformat() if self.started_at else None,
                "finished_at":  self.finished_at.isoformat() if self.finished_at else None,
                "error":        self.error,
            }


_run_state = RunState()
_pipeline_lock = threading.Lock()


# ── Background runner wrapper ─────────────────────────────────────────────────

def _run_pipeline_background(manual: bool, email: str | None) -> None:
    """Runs the pipeline in a background thread, updating _run_state at each stage."""
    if not _pipeline_lock.acquire(blocking=False):
        log.warning("Pipeline trigger ignored — a run is already in progress.")
        return

    _run_state.start()
    captured_html: Optional[str] = None
    captured_subject: Optional[str] = None

    try:
        from app.runner import run  # deferred to avoid circular imports

        # Inject progress callbacks into the runner
        def on_stage(stage: str, msg: str = ""):
            _run_state.advance(stage, msg)

        def on_email_ready(html: str, subject: str):
            nonlocal captured_html, captured_subject
            captured_html    = html
            captured_subject = subject

        run(
            manual=manual,
            target_email=email,
            on_stage=on_stage,
            on_email_ready=on_email_ready,
        )
        _run_state.finish(html=captured_html, subject=captured_subject)

    except Exception as exc:
        log.error("Background pipeline run failed: %s", exc, exc_info=True)
        _run_state.fail(str(exc))
    finally:
        _pipeline_lock.release()


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/run", response_model=PipelineRunResponse, status_code=status.HTTP_202_ACCEPTED)
def trigger_pipeline(
    background_tasks: BackgroundTasks,
    manual: bool = Query(True, description="If true, runs immediately without checking digest_time"),
    email: str | None = Query(None, description="Target user email"),
):
    """
    Trigger an on-demand pipeline run (async, 202 Accepted).
    Poll GET /api/v1/pipeline/run-state for live progress.
    """
    if _pipeline_lock.locked():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A pipeline run is already in progress. Please wait for it to finish.",
        )

    background_tasks.add_task(_run_pipeline_background, manual=manual, email=email)
    log.info("Pipeline run triggered via API (manual=%s, email=%s)", manual, email)

    return PipelineRunResponse(
        message="Pipeline run started. Poll /api/v1/pipeline/run-state for progress.",
        started_at=datetime.now(timezone.utc),
    )


@router.get("/run-state")
def get_run_state():
    """
    Returns the current pipeline run state.
    Poll this every 2-3 seconds after triggering a run.
    """
    return _run_state.snapshot()
