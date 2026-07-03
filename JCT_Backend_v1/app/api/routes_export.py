from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.core.exceptions import DocumentNotFoundError
from app.services import document_store, export_service

router = APIRouter()


@router.get("/documents/{document_id}/export/pdf")
async def export_pdf(document_id: str):
    record = document_store.get(document_id)
    if record is None or record.document is None:
        raise DocumentNotFoundError(f"Document {document_id} not found")
    path = record.export_paths.get("pdf")
    if path is None or not Path(path).exists():
        path = export_service.export_pdf(document_id)
    return FileResponse(path, filename=Path(path).name, media_type="application/pdf")


@router.get("/documents/{document_id}/export/xlsx")
async def export_xlsx(document_id: str):
    record = document_store.get(document_id)
    if record is None or record.document is None:
        raise DocumentNotFoundError(f"Document {document_id} not found")
    path = record.export_paths.get("xlsx")
    if path is None or not Path(path).exists():
        path = export_service.export_xlsx(document_id)
    return FileResponse(
        path,
        filename=Path(path).name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
