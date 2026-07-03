from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.core.envelope import ok
from app.core.exceptions import DocumentNotFoundError
from app.schemas.document import ClauseRow, PreviewResponse, TranslationResponse
from app.services import document_store, verify_service

router = APIRouter()

_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


@router.get("/documents/{document_id}/source")
async def source(document_id: str):
    """Serve the original uploaded file — used for a real visual preview (pdf.js
    for PDFs, <img> for images), independent of OCR/translation progress.
    """
    record = document_store.get(document_id)
    if record is None or not record.stored_path.exists():
        raise DocumentNotFoundError(f"Document {document_id} not found")
    ext = record.stored_path.suffix.lower()
    media_type = _MEDIA_TYPES.get(ext, "application/octet-stream")
    return FileResponse(record.stored_path, media_type=media_type, filename=record.original_filename)


@router.get("/documents/{document_id}/preview")
async def preview(document_id: str):
    record = document_store.get(document_id)
    if record is None or record.document is None:
        raise DocumentNotFoundError(f"Document {document_id} not found or not processed yet")
    return ok(
        PreviewResponse(
            document=record.document, flagged_count=len(record.document.flagged())
        ).model_dump(mode="json")
    )


@router.get("/documents/{document_id}/translation")
async def translation(document_id: str):
    record = document_store.get(document_id)
    if record is None or record.document is None or not record.translated:
        raise DocumentNotFoundError(f"Document {document_id} has not been translated yet")
    rows = verify_service.build_clause_rows(record.document, record.translator_map)
    return ok(TranslationResponse(clauses=[ClauseRow(**r) for r in rows]).model_dump())
