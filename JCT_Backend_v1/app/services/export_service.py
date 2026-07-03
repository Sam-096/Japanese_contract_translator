"""Download outputs (development.md §12): searchable English PDF + clause Excel table."""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

from app.core.config import get_settings
from app.core.exceptions import DocumentNotFoundError
from app.services import document_store
from app.services.render_service import render_english_pdf
from app.services.verify_service import build_clause_rows

_COLUMNS = ["clause_id", "source_jp", "translation_en", "confidence", "status", "notes"]


def _get_processed_record(document_id: str) -> document_store.DocumentRecord:
    record = document_store.get(document_id)
    if record is None or record.document is None:
        raise DocumentNotFoundError(f"Document {document_id} not found or not processed yet")
    return record


def export_xlsx(document_id: str) -> Path:
    record = _get_processed_record(document_id)
    settings = get_settings()
    rows = build_clause_rows(record.document, record.translator_map)

    wb = Workbook()
    ws = wb.active
    ws.title = "Clauses"
    ws.append(_COLUMNS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append([row[col] for col in _COLUMNS])
    for column_cells in ws.columns:
        length = max(len(str(c.value)) if c.value is not None else 0 for c in column_cells)
        ws.column_dimensions[column_cells[0].column_letter].width = min(max(length + 2, 10), 60)

    out_dir = settings.output_dir / document_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{Path(record.original_filename).stem}.xlsx"
    wb.save(out_path)

    document_store.update(
        document_id, export_paths={**record.export_paths, "xlsx": out_path}
    )
    return out_path


def export_pdf(document_id: str) -> Path:
    record = _get_processed_record(document_id)
    settings = get_settings()
    stem = Path(record.original_filename).stem
    out_path = settings.output_dir / document_id / f"{stem}.en.pdf"
    render_english_pdf(record.document, out_path, title=stem)  # overflow ids: see verify_service for the same check

    document_store.update(
        document_id, export_paths={**record.export_paths, "pdf": out_path}
    )
    return out_path
