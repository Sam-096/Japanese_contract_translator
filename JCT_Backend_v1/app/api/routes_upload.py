from __future__ import annotations

from fastapi import APIRouter, File, UploadFile

from app.core.config import get_settings
from app.core.envelope import ok
from app.core.security import validate_upload
from app.schemas.job import UploadResponse
from app.services import export_service, ingest_service, job_service, translate_service

router = APIRouter()


@router.post("/upload")
async def upload(file: UploadFile = File(...), force_refresh: bool = False):
    """`force_refresh=true` bypasses the translation cache for this document
    only, forcing every clause/cell through a fresh LLM call — see
    app.core.cache. Useful for re-testing after a prompt change without
    flushing the shared cache other requests still rely on."""
    settings = get_settings()
    content = await file.read()
    validate_upload(file.filename, content, settings.max_upload_mb)

    record = ingest_service.save_upload(file.filename, content)
    job = job_service.create_job(record.id)

    def _pipeline() -> None:
        job_service.set_status(job.id, "processing", "Extracting text / running OCR")
        ingest_service.run_ingest(record.id)

        job_service.set_status(job.id, "translating", "Translating clauses")
        translate_service.run_translate(record.id, force_refresh=force_refresh, job_id=job.id)

        job_service.set_status(job.id, "rendering", "Rendering downloadable exports")
        export_service.export_xlsx(record.id)
        export_service.export_pdf(record.id)

        job_service.set_status(job.id, "completed", "Done")

    job_service.submit(job.id, _pipeline)

    return ok(
        UploadResponse(
            document_id=record.id, job_id=job.id, filename=file.filename
        ).model_dump()
    )
