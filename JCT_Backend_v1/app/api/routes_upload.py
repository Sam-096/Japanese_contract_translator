from __future__ import annotations

from fastapi import APIRouter, File, UploadFile

from app.core import proxy
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
    flushing the shared cache other requests still rely on.

    LOW_MEMORY_MODE + HF_SPACE_URL (Render<->HF hybrid, see core/proxy.py):
    a scanned PDF/image is forwarded whole to the paired HF Space instead
    of being processed (or rejected) here — HF creates the actual
    document/job records in the DB both deployments share and owns the
    local files, so nothing further happens on this side for that upload.
    """
    settings = get_settings()
    content = await file.read()
    validate_upload(file.filename, content, settings.max_upload_mb)

    if settings.low_memory_mode and settings.hf_proxy_configured:
        kind = ingest_service.classify_bytes(file.filename, content)
        if kind in ("scanned_pdf", "image"):
            return await proxy.forward_upload_to_hf(file.filename, content)

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
