"""Confidence-gated verification (development.md §8): green/amber/red flags, no
claim of 100% accuracy.

Status combines two independent signals:
  1. OCR/extraction confidence (src/jpdoc/schema.py Block.confidence) — set during
     ingest, before translation ever runs.
  2. Translation-quality heuristics computed here — a block extracted at 100%
     confidence can still get a broken translation (the local 3B model
     occasionally leaks meta-commentary or fails to fully translate a clause).
     Without this check those rows showed green/100% despite an unusable
     translation, which defeats the point of confidence-gated review.
The final status is the worse of the two.
"""
from __future__ import annotations

from jpdoc.schema import BlockType, Document

from app.services.render_service import _BASE_SIZE, _HEADING_SIZE, wrap_at_fixed_size

GREEN = "green"
AMBER = "amber"
RED = "red"

_SEVERITY = {GREEN: 0, AMBER: 1, RED: 2}

_COMMENTARY_PREFIXES = (
    "here is the english translation",
    "here's the english translation",
    "translation:",
    "sure,",
    "certainly,",
)


def confidence_flag(confidence: float) -> str:
    if confidence >= 0.80:
        return GREEN
    if confidence >= 0.60:
        return AMBER
    return RED


def _worse(a: str, b: str) -> str:
    return a if _SEVERITY[a] >= _SEVERITY[b] else b


def _notes_for(text: str) -> str:
    notes = []
    if "[UNREADABLE_KANJI]" in text:
        notes.append("unreadable source text")
    elif "[?]" in text:
        notes.append("low OCR confidence")
    return "; ".join(notes)


def _translation_quality_issue(text_en: str) -> str | None:
    text_en = (text_en or "").strip()
    if not text_en:
        return "empty translation"
    if any("぀" <= ch <= "ヿ" or "一" <= ch <= "鿿" for ch in text_en):
        return "source-language text leaked into the translation"
    if text_en.lower().startswith(_COMMENTARY_PREFIXES):
        return "translator added commentary instead of a clean translation"
    return None


def build_clause_rows(doc: Document, translator_map: dict[str, str] | None = None) -> list[dict]:
    translator_map = translator_map or {}
    rows: list[dict] = []
    for pg in doc.pages:
        for b in sorted(pg.blocks, key=lambda x: x.order):
            translated = b.text_ja is not None
            status = confidence_flag(b.confidence)
            needs_review = b.needs_review
            notes = [n for n in [_notes_for(b.text_ja or b.text or "")] if n]

            if translated:
                quality_issue = _translation_quality_issue(b.text)
                if quality_issue:
                    notes.append(quality_issue)
                    needs_review = True
                    quality_status = RED if quality_issue == "empty translation" else AMBER
                    status = _worse(status, quality_status)

                if b.bbox is not None and b.type != BlockType.TABLE:
                    # Checked at the max readable size; render_english_pdf may
                    # auto-shrink the whole document further to avoid adding
                    # pages, so this is a conservative "worth a second look"
                    # signal rather than a guarantee the exported PDF overflows.
                    base_size = _HEADING_SIZE if b.type == BlockType.HEADING else _BASE_SIZE
                    _, overflowed = wrap_at_fixed_size(
                        b.text, b.bbox.x1 - b.bbox.x0, b.bbox.y1 - b.bbox.y0, base_size
                    )
                    if overflowed:
                        notes.append("translation may not fit the original layout box")
                        needs_review = True
                        status = _worse(status, AMBER)

            rows.append(
                {
                    "clause_id": b.id,
                    "page": b.page,
                    "type": b.type.value if hasattr(b.type, "value") else b.type,
                    "source_jp": b.text_ja if translated else b.text,
                    "translation_en": b.text if translated else None,
                    "confidence": round(b.confidence, 3),
                    "status": status,
                    "needs_review": needs_review,
                    "translator": translator_map.get(b.id, "local_ollama"),
                    "notes": "; ".join(notes),
                }
            )
    return rows
