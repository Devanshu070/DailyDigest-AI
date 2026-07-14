"""
app/api/routes/pipeline.py — On-demand pipeline trigger endpoint.

POST /api/v1/pipeline/run   → Kick off the full pipeline in a background thread
"""

import logging
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status

from app.schemas import PipelineRunResponse

log = logging.getLogger(__name__)
router = APIRouter(prefix="/pipeline", tags=["Pipeline"])

# Simple lock so only one run can be in-flight at a time.
_pipeline_lock = threading.Lock()


def _run_pipeline_background(manual: bool, email: str | None) -> None:
    """Runs the pipeline in a background thread. Errors are logged, not raised."""
    if not _pipeline_lock.acquire(blocking=False):
        log.warning("Pipeline trigger ignored — a run is already in progress.")
        return
    try:
        from app.runner import run  # deferred import to avoid circular deps at startup
        run(manual=manual, target_email=email)
    except Exception as exc:
        log.error("Background pipeline run failed: %s", exc, exc_info=True)
    finally:
        _pipeline_lock.release()


@router.post("/run", response_model=PipelineRunResponse, status_code=status.HTTP_202_ACCEPTED)
def trigger_pipeline(
    background_tasks: BackgroundTasks,
    manual: bool = Query(True, description="If true, runs immediately for the given email without checking digest_time"),
    email: str | None = Query(None, description="Target user email. Defaults to the value in .env"),
):
    """
    Trigger an on-demand pipeline run.

    The pipeline runs asynchronously in a background thread so this endpoint
    returns immediately with a 202 Accepted. Only one run can be in-flight at
    a time — duplicate requests while a run is active are silently dropped.
    """
    if _pipeline_lock.locked():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A pipeline run is already in progress. Please wait for it to finish.",
        )

    background_tasks.add_task(_run_pipeline_background, manual=manual, email=email)
    log.info("Pipeline run triggered via API (manual=%s, email=%s)", manual, email)

    return PipelineRunResponse(
        message="Pipeline run started. Check server logs for progress.",
        started_at=datetime.now(timezone.utc),
    )
