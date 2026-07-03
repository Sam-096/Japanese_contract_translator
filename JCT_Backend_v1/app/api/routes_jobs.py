from __future__ import annotations

from fastapi import APIRouter

from app.core.envelope import ok
from app.core.exceptions import JobNotFoundError
from app.schemas.job import JobStatusResponse
from app.services import job_service

router = APIRouter()


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = job_service.get_job(job_id)
    if job is None:
        raise JobNotFoundError(f"Job {job_id} not found")
    return ok(
        JobStatusResponse(
            id=job.id,
            document_id=job.document_id,
            status=job.status,
            progress_message=job.progress_message,
            error=job.error,
        ).model_dump()
    )
