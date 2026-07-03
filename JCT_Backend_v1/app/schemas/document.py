from __future__ import annotations

from typing import Optional

from jpdoc.schema import Document
from pydantic import BaseModel


class PreviewResponse(BaseModel):
    document: Document
    flagged_count: int


class ClauseRow(BaseModel):
    clause_id: str
    page: int
    type: str
    source_jp: Optional[str] = None
    translation_en: Optional[str] = None
    confidence: float
    status: str
    needs_review: bool
    translator: str
    notes: str


class TranslationResponse(BaseModel):
    clauses: list[ClauseRow]
