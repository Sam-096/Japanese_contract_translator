"""Stage 1 — ingest & classify, plus the digital-PDF text path (2a).

Efficiency rule #1: NEVER OCR text we can extract directly. A digital PDF text
layer is exact and free, so we always try it first and only fall back to OCR for
pages that have no usable text.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

import fitz  # PyMuPDF

from .config import MIN_PDF_CHARS_PER_PAGE
from .schema import BBox, Block, BlockType, Document, Page, Source, TableCell

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}

_ROTATION_TOLERANCE_DEG = 3.0


def _is_rotated(line_dir: tuple[float, float]) -> bool:
    dx, dy = line_dir
    angle = abs(math.degrees(math.atan2(dy, dx))) % 90
    return min(angle, 90 - angle) > _ROTATION_TOLERANCE_DEG


def _cell_text_from_spans(page, rect) -> str:
    """Extract text within `rect` directly from page spans, skipping any
    diagonally-rotated line (watermark/stamp text).

    tbl.extract() pulls in ANY text overlapping a cell's rectangle regardless
    of rotation — on a real contract with a diagonal watermark stamped across
    both tables, that meant fragments of the watermark ("Ố", "Ậ", "S", "T",
    "H"...) got interleaved mid-word into unrelated cells, corrupting both
    the transcription and the translation input. Genuine document text is
    virtually always axis-aligned, so filtering by rotation is safe and
    doesn't touch the underlying PDF (unlike redaction, which was tried first
    and rejected — apply_redactions() corrupted adjacent legitimate text in
    the same cell, truncating it mid-word).
    """
    lines_text = []
    for block in page.get_text("dict", clip=rect).get("blocks", []):
        for line in block.get("lines", []):
            if _is_rotated(line.get("dir", (1.0, 0.0))):
                continue
            line_text = "".join(s["text"] for s in line.get("spans", []))
            if line_text.strip():
                lines_text.append(line_text)
    return "\n".join(lines_text).strip()


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def classify(path: Path) -> str:
    """Return 'image', 'digital_pdf', or 'scanned_pdf'."""
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext != ".pdf":
        raise ValueError(f"Unsupported input type: {ext}")
    # Decide digital vs scanned by sampling text content.
    with fitz.open(path) as doc:
        chars = sum(len(p.get_text("text")) for p in doc)
    return "digital_pdf" if chars >= MIN_PDF_CHARS_PER_PAGE else "scanned_pdf"


def _bbox_center_inside(bbox: tuple[float, float, float, float], region: tuple[float, float, float, float]) -> bool:
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    return region[0] <= cx <= region[2] and region[1] <= cy <= region[3]


def _extract_tables(page) -> list[Block]:
    """Detect tables via PyMuPDF find_tables() and capture per-cell geometry
    so layout-preserving export can reconstruct the grid, not just flat text.

    Cell text is pulled directly from spans (`_cell_text_from_spans`) rather
    than `tbl.extract()`, which includes any overlapping text regardless of
    rotation — see `_cell_text_from_spans` docstring.
    """
    try:
        found = page.find_tables()
    except Exception:
        return []

    blocks: list[Block] = []
    for tbl in found.tables:
        cells: list[TableCell] = []
        table_rows: list[list[str]] = []
        for r, row in enumerate(tbl.rows):
            row_texts: list[str] = []
            for c, rect in enumerate(row.cells):
                if rect is None:
                    row_texts.append("")
                    continue
                text = _cell_text_from_spans(page, rect)
                row_texts.append(text)
                cells.append(
                    TableCell(
                        row=r, col=c,
                        bbox=BBox(x0=rect[0], y0=rect[1], x1=rect[2], y1=rect[3]),
                        text=text,
                    )
                )
            table_rows.append(row_texts)

        if not any(any(row) for row in table_rows):
            continue
        blocks.append(
            Block(
                type=BlockType.TABLE,
                text="\n".join("\t".join(r) for r in table_rows),
                bbox=BBox(x0=tbl.bbox[0], y0=tbl.bbox[1], x1=tbl.bbox[2], y1=tbl.bbox[3]),
                table=table_rows,
                cells=cells or None,
                source=Source.PDF_TEXT,
                confidence=1.0,
                id="",  # assigned after reading-order sort, see load_pdf_text
                page=0,  # overwritten with the real 1-based page number there
            )
        )
    return blocks


def load_pdf_text(path: Path) -> tuple[Document, list[int]]:
    """Extract the text layer. Returns (Document, pages_needing_ocr).

    Pages with too little text are left empty here and reported so the OCR stage
    can rasterise and process only those pages (region/page gating, efficiency #2).
    Tables are detected separately (find_tables()) so their cells keep real
    positions instead of collapsing into flat paragraph text.
    """
    doc = Document(source_path=str(path), sha256=sha256_of(path), kind="digital_pdf")
    needs_ocr: list[int] = []
    with fitz.open(path) as pdf:
        for pi, page in enumerate(pdf, start=1):
            pg = Page(number=pi, width=page.rect.width, height=page.rect.height)

            table_blocks = _extract_tables(page)
            table_regions = [
                (b.bbox.x0, b.bbox.y0, b.bbox.x1, b.bbox.y1) for b in table_blocks if b.bbox
            ]

            raw_blocks = page.get_text("blocks")  # (x0,y0,x1,y1,text,bno,btype)
            text_chars = 0
            candidates: list[tuple[float, float, Block]] = []
            for (x0, y0, x1, y1, text, *_rest) in raw_blocks:
                text = (text or "").strip()
                if not text:
                    continue
                if any(_bbox_center_inside((x0, y0, x1, y1), region) for region in table_regions):
                    continue  # already captured as part of a detected table
                text_chars += len(text)
                candidates.append(
                    (y0, x0, Block(
                        type=BlockType.PARAGRAPH,
                        text=text,
                        bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
                        source=Source.PDF_TEXT,
                        confidence=1.0,
                        id="",
                        page=0,
                    ))
                )
            for b in table_blocks:
                candidates.append((b.bbox.y0, b.bbox.x0, b))
                text_chars += sum(len(c.text) for c in (b.cells or []))

            candidates.sort(key=lambda item: (item[0], item[1]))
            for order, (_, _, block) in enumerate(candidates):
                block.id = f"p{pi}-b{order:02d}"
                block.page = pi
                block.order = order
                pg.blocks.append(block)

            if text_chars < MIN_PDF_CHARS_PER_PAGE:
                needs_ocr.append(pi)
            doc.pages.append(pg)
    return doc, needs_ocr
