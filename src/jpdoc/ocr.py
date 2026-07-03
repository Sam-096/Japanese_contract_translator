"""Stage 3 — OCR cascade (accuracy-ordered, with confidence gating).

Order of attempt per page/region:
  (i)   YomiToku   — JP-native detect+recognize+layout+tables (PRIMARY)
  (ii)  manga-ocr  — fallback for lines YomiToku returns low-confidence on
  (iii) confidence — lines still below threshold get the [?]/[UNREADABLE] flag
  (iv)  handwriting/flagged -> Tier-B VLM stub (recorded for later recovery)

Models are loaded lazily and cached module-level so the (slow, CPU) weight load
happens at most once per process — important on this hardware.
"""
from __future__ import annotations

import numpy as np

from .config import CONFIDENCE_THRESHOLD, LOWCONF, RASTER_DPI, UNREADABLE
from .schema import BBox, Block, BlockType, Source, TableCell

# ---- lazy singletons -------------------------------------------------------
_yomitoku = None
_manga = None


def _get_yomitoku():
    global _yomitoku
    if _yomitoku is None:
        from yomitoku import DocumentAnalyzer  # imported lazily

        # device="cpu" — this machine has no usable GPU.
        _yomitoku = DocumentAnalyzer(visualize=False, device="cpu")
    return _yomitoku


def _get_manga():
    global _manga
    if _manga is None:
        from manga_ocr import MangaOcr

        _manga = MangaOcr()
    return _manga


# ---- cascade ---------------------------------------------------------------
def ocr_image(img_bgr: np.ndarray, page: int, dpi: int = RASTER_DPI) -> list[Block]:
    """Run the cascade on one preprocessed page image; return ordered Blocks.

    YomiToku returns box coordinates in raster pixel space (the resolution the
    page/image was rasterised at). Everything downstream (Page.width/height,
    digital-PDF bboxes, the PDF renderer) works in PDF points, so every bbox
    built here is scaled px -> pt using the same DPI the image was rasterised
    at (see raster.py / pipeline.py) — this keeps geometry consistent enough
    to reconstruct layout regardless of source (digital text vs OCR).
    """
    scale = 72.0 / dpi

    def _bbox(box) -> BBox:
        return BBox(x0=box[0] * scale, y0=box[1] * scale, x1=box[2] * scale, y1=box[3] * scale)

    blocks: list[Block] = []
    results, _ = _get_yomitoku()(img_bgr)

    order = 0
    # Tables first (YomiToku exposes them structured) for layout fidelity.
    for tbl in getattr(results, "tables", []) or []:
        n_row = getattr(tbl, "n_row", 0) or 0
        n_col = getattr(tbl, "n_col", 0) or 0
        cell_objs = getattr(tbl, "cells", []) or []
        cells = [
            TableCell(
                row=c.row, col=c.col,
                row_span=getattr(c, "row_span", 1) or 1,
                col_span=getattr(c, "col_span", 1) or 1,
                bbox=_bbox(c.box),
                text=c.contents or "",
            )
            for c in cell_objs
            if getattr(c, "box", None)
        ]
        rows: list[list[str]] = [["" for _ in range(n_col)] for _ in range(n_row)]
        for c in cells:
            if 0 <= c.row < n_row and 0 <= c.col < n_col:
                rows[c.row][c.col] = c.text
        if not any(any(r) for r in rows):
            rows = [[c.contents or "" for c in row] for row in getattr(tbl, "rows", [])]

        if rows:
            box = getattr(tbl, "box", None)
            bbox = _bbox(box) if box else None
            blocks.append(
                Block(
                    id=f"p{page}-t{order:02d}",
                    page=page,
                    type=BlockType.TABLE,
                    text="\n".join("\t".join(r) for r in rows),
                    bbox=bbox,
                    table=rows,
                    cells=cells or None,
                    source=Source.OCR_YOMITOKU,
                    confidence=1.0,
                    order=order,
                )
            )
            order += 1

    for para in getattr(results, "paragraphs", []) or []:
        text = (para.contents or "").strip()
        conf = float(getattr(para, "score", 1.0) or 1.0)
        box_px = getattr(para, "box", None)
        bbox_px = BBox(x0=box_px[0], y0=box_px[1], x1=box_px[2], y1=box_px[3]) if box_px else None
        source = Source.OCR_YOMITOKU

        # (ii) escalate low-confidence lines to manga-ocr using the crop. Must use
        # PIXEL-space bbox here since it crops the raw raster array, not the
        # point-space bbox stored on the Block below.
        if conf < CONFIDENCE_THRESHOLD and bbox_px is not None:
            text2, conf2 = _manga_retry(img_bgr, bbox_px)
            if conf2 > conf:
                text, conf, source = text2, conf2, Source.OCR_MANGA

        needs_review = conf < CONFIDENCE_THRESHOLD
        if needs_review:
            # (iii) flag rather than silently guess. Tier-B VLM (iv) handles later.
            text = f"{text} {LOWCONF}" if text else UNREADABLE

        blocks.append(
            Block(
                id=f"p{page}-b{order:02d}",
                page=page,
                type=BlockType.PARAGRAPH,
                text=text,
                bbox=_bbox(box_px) if box_px else None,
                source=source,
                confidence=conf,
                needs_review=needs_review,
                order=order,
            )
        )
        order += 1
    return blocks


def _manga_retry(img_bgr: np.ndarray, bbox: BBox) -> tuple[str, float]:
    """Crop the region and re-OCR with manga-ocr. Returns (text, confidence)."""
    from PIL import Image

    x0, y0, x1, y1 = int(bbox.x0), int(bbox.y0), int(bbox.x1), int(bbox.y1)
    crop = img_bgr[max(0, y0):y1, max(0, x0):x1]
    if crop.size == 0:
        return "", 0.0
    pil = Image.fromarray(crop[:, :, ::-1] if crop.ndim == 3 else crop)
    text = _get_manga()(pil).strip()
    # manga-ocr gives no score; treat a non-empty result as moderately confident.
    return (text, 0.85) if text else ("", 0.0)
