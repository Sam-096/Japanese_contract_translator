"""Upload handling + Phase-1a ingest (detect -> extract/OCR -> canonical Document).

Wraps jpdoc.pipeline.process — the same content-hash-cached entry point the CLI uses.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from jpdoc import pipeline
from jpdoc.ingest import classify

from app.core.config import get_settings
from app.core.exceptions import (
    CorruptFileError,
    PasswordProtectedPdfError,
    ScannedDocumentUnsupportedError,
)
from app.services import document_store


def save_upload(filename: str, content: bytes) -> document_store.DocumentRecord:
    settings = get_settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    document_id = str(uuid.uuid4())
    ext = Path(filename).suffix.lower()
    stored_path = settings.upload_dir / f"{document_id}{ext}"
    stored_path.write_bytes(content)

    record = document_store.DocumentRecord(
        id=document_id, original_filename=filename, stored_path=stored_path
    )
    document_store.create(record)
    return record


def _check_pdf_readable(path: Path) -> None:
    if path.suffix.lower() != ".pdf":
        return
    import fitz

    try:
        with fitz.open(path) as pdf:
            if pdf.needs_pass:
                raise PasswordProtectedPdfError(
                    "This file appears to be password protected."
                )
    except PasswordProtectedPdfError:
        raise
    except Exception as exc:
        raise CorruptFileError(f"Could not open PDF: {exc}") from exc


def _check_low_memory_support(path: Path) -> None:
    """LOW_MEMORY_MODE guard: bail before pipeline.process() would trigger
    the OCR cascade (YomiToku + manga-ocr + torch) for a scanned PDF or raw
    image — measured to need far more RAM than a 512MB instance provides
    (digital PDFs, PyMuPDF-only, measurably don't: see JCT_Backend_v1
    memory testing, ~120-165MB across real documents). classify() is cheap
    (extension check, or a text-layer char count for PDFs) — no ML models
    touched here, safe to call unconditionally.
    """
    kind = classify(path)
    if kind in ("scanned_pdf", "image"):
        raise ScannedDocumentUnsupportedError(
            f"Rejected {kind} document under LOW_MEMORY_MODE — the OCR cascade "
            "needs more RAM than this deployment provides."
        )


def run_ingest(document_id: str) -> None:
    settings = get_settings()
    record = document_store.get(document_id)
    if record is None:
        raise ValueError(f"Unknown document {document_id}")

    _check_pdf_readable(record.stored_path)

    if settings.low_memory_mode:
        _check_low_memory_support(record.stored_path)

    doc = pipeline.process(record.stored_path, settings.cache_dir)
    document_store.update(document_id, document=doc, kind=doc.kind)
