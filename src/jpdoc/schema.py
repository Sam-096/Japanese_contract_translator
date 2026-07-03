"""Canonical intermediate schema — the single, medium-independent source of truth.

Every input (digital PDF, scanned PDF, image) is normalised into a `Document`.
Translation (Phase 1b) and vector-less RAG (Phase 2) read ONLY this object, never
raw OCR output. Keeping one schema is the main lever for both accuracy (stable
reading order, dedup) and token efficiency (we translate clean, deduplicated text).
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Source(str, Enum):
    PDF_TEXT = "pdf_text"        # extracted from a digital PDF text layer (exact)
    OCR_YOMITOKU = "ocr_yomitoku"
    OCR_MANGA = "ocr_manga"
    OCR_TESSERACT = "ocr_tesseract"
    VLM = "vlm"                  # Tier-B handwriting recovery (stub for now)


class BlockType(str, Enum):
    PARAGRAPH = "paragraph"
    HEADING = "heading"
    TABLE = "table"
    SEAL = "seal"               # hanko / stamp region
    LIST = "list"
    UNKNOWN = "unknown"


class BBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


class TableCell(BaseModel):
    """Per-cell geometry for layout-preserving table reconstruction.

    Optional and additive: populated when the OCR/extraction path can supply real
    cell positions (yomitoku for scanned/image pages, PyMuPDF find_tables() for
    digital PDFs). When absent, table rendering falls back to a flowed grid.
    """
    row: int
    col: int
    row_span: int = 1
    col_span: int = 1
    bbox: BBox
    text: str = ""


class Block(BaseModel):
    """One logical unit of content with provenance and a confidence score."""
    id: str                                   # stable id, e.g. "p1-b03"
    page: int
    type: BlockType = BlockType.PARAGRAPH
    text: str = ""                            # active text (JP before translate, EN after)
    text_ja: Optional[str] = None            # original Japanese, set by translate.py
    bbox: Optional[BBox] = None
    source: Source = Source.PDF_TEXT
    confidence: float = 1.0                   # 0..1; <THRESHOLD -> flagged
    needs_review: bool = False                # carries the [?]/[UNREADABLE] flag
    order: int = 0                            # reading order within the page
    # table rows kept as list-of-rows of cell strings when type == TABLE
    table: Optional[list[list[str]]] = None
    # per-cell geometry for TABLE blocks, parallel to `table` when available
    cells: Optional[list[TableCell]] = None


class Page(BaseModel):
    number: int
    width: float = 0.0
    height: float = 0.0
    blocks: list[Block] = Field(default_factory=list)


class Document(BaseModel):
    source_path: str
    sha256: str                               # content hash -> cache key (efficiency)
    kind: str                                 # "digital_pdf" | "scanned_pdf" | "image"
    pages: list[Page] = Field(default_factory=list)

    def flagged(self) -> list[Block]:
        """All low-confidence blocks needing human/VLM review."""
        return [b for pg in self.pages for b in pg.blocks if b.needs_review]

    def all_text(self) -> str:
        out: list[str] = []
        for pg in self.pages:
            for b in sorted(pg.blocks, key=lambda x: x.order):
                out.append(b.text)
        return "\n".join(out)
