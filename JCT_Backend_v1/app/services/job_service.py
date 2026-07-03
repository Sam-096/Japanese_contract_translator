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
from concurrent.futures import ThreadPoolExecutor
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


def set_status(job_id: str, status: JobStatus, message: str) -> None:
    _update(job_id, status=status, progress_message=message)


def set_error(job_id: str, code: str, message: str, details: dict | None = None) -> None:
    from app.core import notifications
    from app.core.error_catalog import present

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


def submit(job_id: str, fn: Callable[[], None]) -> None:
    def _run() -> None:
        try:
            fn()
        except AppError as exc:
            set_error(job_id, exc.code, exc.message, exc.details)
        except Exception as exc:  # safety net so a bug never leaves a job stuck "processing"
            set_error(job_id, "INTERNAL_ERROR", str(exc), {"traceback": traceback.format_exc()})

    _executor.submit(_run)
