"""Document registry: Postgres-backed when DATABASE_URL is configured (see
JCT_Backend_v1/db/schema.sql) so records survive a restart and are visible across
worker processes; falls back to in-process in-memory storage otherwise
(Phase 1 behavior — single-process only, lost on restart).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock

from jpdoc.schema import Document

from app.core.config import get_settings


@dataclass
class DocumentRecord:
    id: str
    original_filename: str
    stored_path: Path
    kind: str | None = None
    document: Document | None = None
    translated: bool = False
    translator_map: dict[str, str] = field(default_factory=dict)
    export_paths: dict[str, Path] = field(default_factory=dict)


# ---- in-memory fallback (DATABASE_URL not set) ------------------------------
_records: dict[str, DocumentRecord] = {}
_lock = Lock()


def _create_memory(record: DocumentRecord) -> None:
    with _lock:
        _records[record.id] = record


def _get_memory(document_id: str) -> DocumentRecord | None:
    with _lock:
        return _records.get(document_id)


def _update_memory(document_id: str, **kwargs) -> None:
    with _lock:
        record = _records.get(document_id)
        if record is None:
            return
        for key, value in kwargs.items():
            setattr(record, key, value)


# ---- Postgres-backed ---------------------------------------------------------
def _row_to_record(row: tuple) -> DocumentRecord:
    (doc_id, original_filename, stored_path, kind, document_json,
     translated, translator_map, export_paths) = row
    return DocumentRecord(
        id=str(doc_id),
        original_filename=original_filename,
        stored_path=Path(stored_path),
        kind=kind,
        document=Document.model_validate(document_json) if document_json else None,
        translated=translated,
        translator_map=translator_map or {},
        export_paths={k: Path(v) for k, v in (export_paths or {}).items()},
    )


def _create_db(record: DocumentRecord) -> None:
    from app.core.db import get_conn

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO documents (id, original_filename, stored_path, kind,
                document_json, translated, translator_map, export_paths)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                record.id, record.original_filename, str(record.stored_path), record.kind,
                json.dumps(record.document.model_dump(mode="json")) if record.document else None,
                record.translated,
                json.dumps(record.translator_map),
                json.dumps({k: str(v) for k, v in record.export_paths.items()}),
            ),
        )
        conn.commit()


def _get_db(document_id: str) -> DocumentRecord | None:
    from app.core.db import get_conn

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, original_filename, stored_path, kind, document_json,
                   translated, translator_map, export_paths
            FROM documents WHERE id = %s
            """,
            (document_id,),
        )
        row = cur.fetchone()
        return _row_to_record(row) if row else None


_COLUMN_MAP = {
    "kind": "kind",
    "document": "document_json",
    "translated": "translated",
    "translator_map": "translator_map",
    "export_paths": "export_paths",
}


def _update_db(document_id: str, **kwargs) -> None:
    sets, values = [], []
    for key, value in kwargs.items():
        column = _COLUMN_MAP.get(key)
        if column is None:
            continue
        if key == "document":
            value = json.dumps(value.model_dump(mode="json")) if value else None
        elif key == "translator_map":
            value = json.dumps(value)
        elif key == "export_paths":
            value = json.dumps({k: str(v) for k, v in value.items()})
        sets.append(f"{column} = %s")
        values.append(value)
    if not sets:
        return
    sets.append("updated_at = now()")
    values.append(document_id)

    from app.core.db import get_conn

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"UPDATE documents SET {', '.join(sets)} WHERE id = %s", values)
        conn.commit()


# ---- public interface ---------------------------------------------------------
def create(record: DocumentRecord) -> None:
    if get_settings().database_configured:
        _create_db(record)
    else:
        _create_memory(record)


def get(document_id: str) -> DocumentRecord | None:
    if get_settings().database_configured:
        return _get_db(document_id)
    return _get_memory(document_id)


def update(document_id: str, **kwargs) -> None:
    if get_settings().database_configured:
        _update_db(document_id, **kwargs)
    else:
        _update_memory(document_id, **kwargs)
