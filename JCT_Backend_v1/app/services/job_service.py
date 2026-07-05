"""Background job runner + registry. Job EXECUTION (`submit`) always runs in an
in-process ThreadPoolExecutor regardless of storage backend — OCR/translation
are slow (5-30s/page OCR, 1-5s/block translation on CPU) — far past a typical
HTTP timeout, so /upload returns immediately and the frontend polls
GET /jobs/{id}. Job STATE is Postgres-backed when DATABASE_URL is configured
(see JCT_Backend_v1/db/schema.sql), so status survives a restart and is visible
across worker processes; falls back to in-memory otherwise (Phase 1 behavior).
Swap `submit`'s executor for Celery+Redis if this needs to scale past one
process's worker pool.

`set_error` splits every failure into a user-safe half and a developer-only
half (see core/error_catalog.py, core/notifications.py): the client only
ever receives the catalog's friendly message, never the raw exception text
or a traceback — those go to a Slack alert (when configured) and the server
log only.
"""
from __future__ import annotations

import json
import logging
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from threading import Lock
from typing import Callable, Literal

from app.core.config import get_settings
from app.core.exceptions import AppError

logger = logging.getLogger("app.job_service")

JobStatus = Literal[
    "queued", "processing", "translating", "rendering", "completed", "failed"
]


@dataclass
class Job:
    id: str
    document_id: str
    status: JobStatus = "queued"
    progress_message: str = "Queued"
    error: dict | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


# ---- in-memory fallback (DATABASE_URL not set) ------------------------------
_jobs: dict[str, Job] = {}
_lock = Lock()


def _create_memory(job: Job) -> None:
    with _lock:
        _jobs[job.id] = job


def _get_memory(job_id: str) -> Job | None:
    with _lock:
        return _jobs.get(job_id)


def _update_memory(job_id: str, **kwargs) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        for key, value in kwargs.items():
            setattr(job, key, value)
        job.updated_at = time.time()


# ---- Postgres-backed ---------------------------------------------------------
def _create_db(job: Job) -> None:
    from app.core.db import get_conn

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO jobs (id, document_id, status, progress_message) VALUES (%s, %s, %s, %s)",
            (job.id, job.document_id, job.status, job.progress_message),
        )
        conn.commit()


def _get_db(job_id: str) -> Job | None:
    from app.core.db import get_conn

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, document_id, status, progress_message, error, "
            "extract(epoch from created_at), extract(epoch from updated_at) "
            "FROM jobs WHERE id = %s",
            (job_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        job_id_, document_id, status, progress_message, error, created_at, updated_at = row
        return Job(
            id=str(job_id_), document_id=str(document_id), status=status,
            progress_message=progress_message, error=error,
            created_at=float(created_at), updated_at=float(updated_at),
        )


def _update_db(job_id: str, **kwargs) -> None:
    sets, values = [], []
    for key in ("status", "progress_message", "error"):
        if key in kwargs:
            value = kwargs[key]
            if key == "error" and value is not None:
                value = json.dumps(value)
            sets.append(f"{key} = %s")
            values.append(value)
    if not sets:
        return
    sets.append("updated_at = now()")
    values.append(job_id)

    from app.core.db import get_conn

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id = %s", values)
        conn.commit()


# ---- public interface ---------------------------------------------------------
def create_job(document_id: str) -> Job:
    job = Job(id=str(uuid.uuid4()), document_id=document_id)
    if get_settings().database_configured:
        _create_db(job)
    else:
        _create_memory(job)
    return job


def get_job(job_id: str) -> Job | None:
    if get_settings().database_configured:
        return _get_db(job_id)
    return _get_memory(job_id)


def _update(job_id: str, **kwargs) -> None:
    if get_settings().database_configured:
        _update_db(job_id, **kwargs)
    else:
        _update_memory(job_id, **kwargs)


_TERMINAL_STATUSES = {"completed", "failed"}


def _is_terminal(job_id: str) -> bool:
    """Once a job reaches completed/failed, nothing should mutate it again.
    Guards against a real race: job_service.submit's timeout watchdog
    (below) marks a job failed after it exceeds JOB_TIMEOUT_SECONDS, but the
    original worker thread — Python can't forcibly kill a thread — may
    still be running and could otherwise overwrite that with a stale
    "completed" (or a second, different "failed") once it eventually
    finishes. Reproduced live: a job manually held past its timeout then
    later called set_status("completed") and would have silently clobbered
    the correctly-recorded timeout error without this check.
    """
    job = get_job(job_id)
    return job is not None and job.status in _TERMINAL_STATUSES


def set_status(job_id: str, status: JobStatus, message: str) -> None:
    if _is_terminal(job_id):
        logger.warning(
            "job %s: ignoring set_status(%r) — already in a terminal state", job_id, status
        )
        return
    _update(job_id, status=status, progress_message=message)


def set_error(job_id: str, code: str, message: str, details: dict | None = None) -> None:
    from app.core import notifications
    from app.core.error_catalog import present

    if _is_terminal(job_id):
        logger.warning("job %s: ignoring set_error(%r) — already in a terminal state", job_id, code)
        return

    presentation = present(code)
    logger.warning("job %s failed [%s]: %s", job_id, code, message)

    _update(
        job_id,
        status="failed",
        progress_message=presentation.title,
        # Client-facing error is ALWAYS the catalog's safe message — never
        # the raw exception text, and `details` (which can carry a full
        # traceback, see `submit` below) is dropped entirely rather than
        # forwarded, even though it was accepted as a parameter here.
        error={
            "code": code,
            "message": presentation.message,
            "severity": presentation.severity,
            "details": {},
        },
    )

    if presentation.alert_slack:
        detail_text = message
        traceback_text = (details or {}).get("traceback")
        if traceback_text:
            detail_text += f"\n```{traceback_text[-1500:]}```"
        notifications.send_slack_alert(
            severity=presentation.severity,
            title=f"{presentation.title} ({code})",
            detail=detail_text,
            job_id=job_id,
        )


_executor = ThreadPoolExecutor(max_workers=2)
# Separate, larger pool for timeout watchdogs (see submit below) — a watchdog
# just blocks on future.result(timeout=...), it doesn't compute anything, so
# it's cheap to run many concurrently. Using the SAME 2-worker _executor for
# both would halve real job concurrency, since every job would occupy one
# worker slot for the job itself and implicitly contend for another via its
# own watchdog.
_watchdog_executor = ThreadPoolExecutor(max_workers=16)


def submit(job_id: str, fn: Callable[[], None]) -> None:
    def _run() -> None:
        try:
            fn()
        except AppError as exc:
            set_error(job_id, exc.code, exc.message, exc.details)
        except Exception as exc:  # safety net so a bug never leaves a job stuck "processing"
            set_error(job_id, "INTERNAL_ERROR", str(exc), {"traceback": traceback.format_exc()})

    future = _executor.submit(_run)
    _watchdog_executor.submit(_watch_for_timeout, job_id, future)


def _watch_for_timeout(job_id: str, future) -> None:
    """Waits up to JOB_TIMEOUT_SECONDS for `future` to finish; if it hasn't,
    force-marks the job as timed out rather than leaving it in "processing"
    forever (the actual incident this exists to prevent — see module
    docstring). Real limitation: Python cannot forcibly kill a running
    thread, so a genuinely hung `_run()` keeps executing in the background
    even after this fires — this fixes the user-facing symptom (a job
    stuck forever with zero feedback) but not the underlying leaked thread.
    Safe to call set_error() unconditionally here even if `_run()` finishes
    (or fails) right at the timeout boundary — set_error/set_status both
    no-op on an already-terminal job (see _is_terminal).
    """
    settings = get_settings()
    try:
        future.result(timeout=settings.job_timeout_seconds)
    except FutureTimeoutError:
        set_error(
            job_id,
            "TRANSLATION_TIMEOUT",
            f"Job exceeded the {settings.job_timeout_seconds:.0f}s processing "
            "timeout without completing — likely a crashed or hung worker.",
        )
    except Exception:
        pass  # _run()'s own try/except already handles/logs any real failure
