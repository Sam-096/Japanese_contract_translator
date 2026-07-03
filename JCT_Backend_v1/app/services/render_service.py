"""Layout-preserving English PDF rendering.

Per the "Layout-Preserving Translation Output" spec: the original Japanese
document's geometry (page size, per-block bbox, per-cell table geometry — see
src/jpdoc/schema.py Block.bbox / Block.cells, populated by ingest.py and
ocr.py) is the template. Translated text is drawn using that geometry rather
than reflowed as a plain text dump, so headings, paragraph order, tables, and
signature-block placement all survive translation.

Three things were tried and rejected before this design, all from testing
against real contracts:

1. Per-block auto-shrink-to-fit font size: sibling paragraphs that were the
   same size in the source ended up rendered at visibly different sizes
   purely because one translated line happened to be shorter than another.
   Font size is document-uniform instead.

2. Drawing every block at its exact original (x, y) position: Japanese
   contracts pack paragraph blocks tightly (small gaps, ~14pt line height),
   and English translations of the same clause typically run 20-40% longer.
   At a fixed font size that means most blocks wrap to 2+ lines, which then
   overlaps the next block drawn at ITS fixed original y-position — the
   output was frequently illegible.

3. Always rendering at the same base size and accepting whatever pagination
   results: works, but grows the page count more than necessary — a size
   that's still perfectly readable often avoids adding pages at all.

The renderer therefore does two passes. Pass 1 is a dry run (no canvas): it
tries a shrinking sequence of uniform document-wide font sizes and, for each,
simulates the flow layout to see whether every source page still fits within
its own original page (no pagination growth). It picks the LARGEST size that
avoids growth; if none do, it falls back to the smallest candidate and
accepts pagination as the final safety net — legal text is never truncated,
only ever pushed onto a continuation page. Pass 2 draws the real PDF at the
chosen size, using the same flow logic: a block starts at
max(original_y0, running_cursor), so a block with extra whitespace before it
in the source keeps that whitespace, but one following an over-long block
gets pushed down instead of overlapping it. Horizontal position (x0/x1) is
always preserved exactly.

Table rows get the same treatment as paragraph blocks, for the same reason:
a fixed original row height was calibrated for a short Japanese form label
(e.g. 業務内容, 4 characters) and cannot hold its English translation
("Nature of Work / Scope of Services..."), so row height grows to fit —
column x-positions/widths are preserved exactly, only row height is dynamic.
A uniform cell font size (derived from the chosen document-wide base size)
is used across the whole table, for the same "no inconsistent sizes between
siblings" reason paragraph blocks use a uniform size.

Blocks without bbox (e.g. a Document cached before this feature existed)
fall back to a simple flowed layout so nothing is ever silently dropped.
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

from jpdoc.schema import Block, BlockType, Document, Page

_BASE_SIZE = 10.0
_HEADING_SIZE = 13.0
_CELL_MIN_SIZE = 5.5
_LEADING_RATIO = 1.18
_BLOCK_GAP = 3.0
_BOTTOM_MARGIN = 15 * mm
_TOP_MARGIN = 15 * mm

# Uniform document-wide sizes tried, largest first, before accepting pagination growth.
_SIZE_CANDIDATES = [10.0, 9.0, 8.0, 7.0, 6.0]


def _cell_size_for(base_size: float) -> float:
    return max(base_size - 2.0, _CELL_MIN_SIZE)

# Helvetica has zero CJK glyph coverage — any Japanese character drawn with it
# silently renders as a black box (.notdef) instead of erroring. Translation
# should always replace Japanese with English, but glossary markers, partial
# translation misses, or an untranslated cell shouldn't corrupt into boxes —
# they should still be legible. HeiseiKakuGo-W5 is one of reportlab's built-in
# standard CID fonts (Adobe-Japan1): no font file to bundle, works the same
# in the Docker/Linux deployment as it does locally.
_CJK_FONT = "HeiseiKakuGo-W5"
pdfmetrics.registerFont(UnicodeCIDFont(_CJK_FONT))


def _needs_cjk_font(text: str) -> bool:
    return any(
        "　" <= ch <= "ヿ"  # CJK punctuation, Hiragana, Katakana
        or "㐀" <= ch <= "鿿"  # CJK Unified Ideographs (+ Ext A)
        or "豈" <= ch <= "﫿"  # CJK Compatibility Ideographs
        or "＀" <= ch <= "￯"  # Halfwidth/Fullwidth forms
        for ch in text
    )


def _resolve_font(text: str, base_font: str) -> str:
    return _CJK_FONT if _needs_cjk_font(text) else base_font


def _wrap_lines(text: str, width: float, size: float, font: str) -> tuple[list[str], str]:
    """Wrap `text`, auto-switching to the CJK fallback font when it contains
    Japanese the translator didn't replace. Returns (lines, font_actually_used).
    """
    text = (text or "").strip()
    if not text:
        return [], font
    resolved = _resolve_font(text, font)
    return simpleSplit(text, resolved, size, max(width, 4.0)), resolved


def wrap_at_fixed_size(
    text: str, width: float, height: float, size: float, font: str = "Helvetica",
) -> tuple[list[str], bool]:
    """Wrap `text` at a FIXED size (no shrinking) inside width x height.
    Returns (wrapped_lines, overflowed) — overflowed means the wrapped text
    is taller than the box, not that anything was cut (nothing ever is).
    Used by verify_service for the review-table warning (no pagination
    concerns there, just "does this fit its original box").
    """
    lines, _ = _wrap_lines(text, width, size, font)
    if not lines:
        return [], False
    block_height = len(lines) * size * _LEADING_RATIO
    return lines, block_height > max(height, 4.0)


def _draw_lines(c: canvas.Canvas | None, lines: list[str], x0: float, y0_top: float,
                 page_height: float, size: float, font: str) -> None:
    if not lines or c is None:
        return
    c.setFont(font, size)
    leading = size * _LEADING_RATIO
    cursor_y = page_height - y0_top - size
    for line in lines:
        c.drawString(x0, cursor_y, line)
        cursor_y -= leading


_CELL_PAD = 2.0


def _cell_lines(text: str, width: float, size: float) -> tuple[list[str], str]:
    return _wrap_lines(text, max(width - 2 * _CELL_PAD, 4.0), size, "Helvetica")


def _draw_cell(c: canvas.Canvas | None, lines: list[str], font: str, x0: float, row_top: float,
                x1: float, row_height: float, page_height: float, size: float) -> None:
    if c is not None:
        c.rect(x0, page_height - (row_top + row_height), x1 - x0, row_height, stroke=1, fill=0)
    _draw_lines(c, lines, x0 + _CELL_PAD, row_top + _CELL_PAD, page_height, size, font)


def _draw_table_block(
    c: canvas.Canvas | None, block: Block, page_height: float, dy: float, cell_size: float,
) -> tuple[float, bool]:
    """Draw the table with per-row height that GROWS to fit translated cell
    text (column x-positions/widths are preserved exactly from the source —
    only row height is dynamic). Mirrors the paragraph-flow fix: a fixed
    original row height was calibrated for short Japanese labels, and a form
    label like 業務内容 (4 chars) routinely translates to a full English
    phrase — forcing that into the original row height silently overlapped
    the row below it. Returns (actual_table_height, overflowed) where
    overflowed means at least one row grew past its original height.
    """
    if block.cells:
        by_row: dict[int, list] = {}
        for cell in block.cells:
            by_row.setdefault(cell.row, []).append(cell)

        table_y0 = min(cell.bbox.y0 for cell in block.cells) + dy
        row_top = table_y0
        overflowed = False

        for row_idx in sorted(by_row):
            cells = by_row[row_idx]
            orig_row_height = max(cell.bbox.y1 - cell.bbox.y0 for cell in cells)
            prepared = []
            needed_height = orig_row_height
            for cell in cells:
                width = cell.bbox.x1 - cell.bbox.x0
                lines, font = _cell_lines(cell.text, width, cell_size)
                content_height = len(lines) * cell_size * _LEADING_RATIO + 2 * _CELL_PAD
                needed_height = max(needed_height, content_height)
                prepared.append((cell, lines, font))

            if needed_height > orig_row_height + 0.5:
                overflowed = True

            for cell, lines, font in prepared:
                _draw_cell(c, lines, font, cell.bbox.x0, row_top, cell.bbox.x1,
                           needed_height, page_height, cell_size)
            row_top += needed_height

        return row_top - table_y0, overflowed

    # No per-cell geometry (fallback): draw a simple flowed grid inside the block bbox,
    # equal column widths preserved, but still with dynamic row growth.
    if not block.table or not block.bbox:
        return 0.0, False
    bbox = block.bbox
    x0, y0, x1 = bbox.x0, bbox.y0 + dy, bbox.x1
    n_cols = max((len(r) for r in block.table), default=1)
    col_w = (x1 - x0) / max(n_cols, 1)
    row_top = y0
    overflowed = False

    for row in block.table:
        orig_row_height = max((bbox.y1 - bbox.y0) / max(len(block.table), 1), cell_size * _LEADING_RATIO)
        prepared = []
        needed_height = orig_row_height
        for col_i, cell_text in enumerate(row):
            lines, font = _cell_lines(cell_text, col_w, cell_size)
            content_height = len(lines) * cell_size * _LEADING_RATIO + 2 * _CELL_PAD
            needed_height = max(needed_height, content_height)
            prepared.append((col_i, lines, font))

        if needed_height > orig_row_height + 0.5:
            overflowed = True

        for col_i, lines, font in prepared:
            cx0 = x0 + col_i * col_w
            _draw_cell(c, lines, font, cx0, row_top, cx0 + col_w, needed_height, page_height, cell_size)
        row_top += needed_height

    return row_top - y0, overflowed


def _flow_fallback(c: canvas.Canvas | None, blocks: list[Block], width: float, height: float,
                    margin: float, base_size: float) -> int:
    """Draw (or, if c is None, just count) bbox-less blocks flowed top-to-bottom.
    Returns how many physical pages this consumed.
    """
    pages_used = 1
    y = height - margin
    for b in blocks:
        text = (b.text or "").strip()
        if not text:
            continue
        prefix = "[REVIEW] " if b.needs_review else ""
        full_text = prefix + text
        font = _resolve_font(full_text, "Helvetica")
        if c is not None:
            c.setFont(font, base_size)
        for line in simpleSplit(full_text, font, base_size, width - 2 * margin):
            if y < margin:
                if c is not None:
                    c.showPage()
                    c.setFont(font, base_size)
                pages_used += 1
                y = height - margin
            if c is not None:
                c.drawString(margin, y, line)
            y -= base_size * _LEADING_RATIO
        y -= 2 * mm
    return pages_used


def _render_document(
    c: canvas.Canvas | None, doc: Document, base_size: float, heading_size: float,
) -> tuple[int, set[str]]:
    """Lay out (and, if c is not None, actually draw) the whole document at a
    given uniform font size. Returns (total_physical_pages, overflowed_block_ids).
    With c=None this is a pure measurement pass — no reportlab Canvas calls.
    """
    cell_size = _cell_size_for(base_size)
    total_pages = 0
    overflowed_ids: set[str] = set()

    for page in doc.pages:
        has_geometry = page.width > 0 and page.height > 0
        page_w, page_h = (page.width, page.height) if has_geometry else A4
        if c is not None:
            c.setPageSize((page_w, page_h))
        pages_for_this_source_page = 1

        if has_geometry:
            positioned = sorted((b for b in page.blocks if b.bbox is not None), key=lambda b: b.order)
            unpositioned = [b for b in page.blocks if b.bbox is None]
        else:
            positioned = []
            unpositioned = page.blocks

        y_cursor = positioned[0].bbox.y0 if positioned else _TOP_MARGIN
        # Once a block spills onto a continuation page, the original absolute
        # y-positions of later blocks (calibrated for the first page) no
        # longer mean anything relative to it — switch to pure flow.
        desynced = False

        for b in positioned:
            bbox = b.bbox
            y0 = y_cursor if desynced else max(bbox.y0, y_cursor)

            if b.type == BlockType.TABLE:
                # Measure first (no drawing) so the page-break decision below
                # accounts for row growth, then draw for real at the chosen y0.
                measured_height, _ = _draw_table_block(None, b, page_h, 0, cell_size)
                if y0 > _TOP_MARGIN and y0 + measured_height > page_h - _BOTTOM_MARGIN:
                    if c is not None:
                        c.showPage()
                        c.setPageSize((page_w, page_h))
                    pages_for_this_source_page += 1
                    y0 = _TOP_MARGIN
                    desynced = True
                actual_height, table_overflowed = _draw_table_block(c, b, page_h, y0 - bbox.y0, cell_size)
                if table_overflowed:
                    overflowed_ids.add(b.id)
                y_cursor = y0 + actual_height + _BLOCK_GAP
                continue

            size = heading_size if b.type == BlockType.HEADING else base_size
            base_font = "Helvetica-Bold" if b.type == BlockType.HEADING else "Helvetica"
            text = ("[REVIEW] " if b.needs_review else "") + (b.text or "")
            lines, font = _wrap_lines(text, bbox.x1 - bbox.x0, size, base_font)
            rendered_height = len(lines) * size * _LEADING_RATIO

            if y0 > _TOP_MARGIN and lines and y0 + rendered_height > page_h - _BOTTOM_MARGIN:
                if c is not None:
                    c.showPage()
                    c.setPageSize((page_w, page_h))
                pages_for_this_source_page += 1
                y0 = _TOP_MARGIN
                desynced = True

            _draw_lines(c, lines, bbox.x0, y0, page_h, size, font)
            if rendered_height > (bbox.y1 - bbox.y0):
                overflowed_ids.add(b.id)
            y_cursor = y0 + max(bbox.y1 - bbox.y0, rendered_height) + _BLOCK_GAP

        if unpositioned:
            # Rare mixed case (a positioned page with a stray bbox-less block):
            # flow it below everything else rather than dropping it.
            pages_for_this_source_page += _flow_fallback(
                c, unpositioned, page_w, page_h, 15 * mm, base_size
            ) - 1

        if c is not None:
            c.showPage()
        total_pages += pages_for_this_source_page

    return total_pages, overflowed_ids


def render_english_pdf(doc: Document, out_path: Path, title: str) -> tuple[Path, set[str]]:
    """Render translated blocks back into the source layout. Returns the output
    path and the set of block ids whose translation grew past its original box
    (still rendered in full — never truncated — just flagged for review).

    First does dry-run measurement passes (no canvas) at decreasing uniform
    font sizes to find the largest size that keeps every source page within
    its own original page count; only if no candidate size achieves that does
    it fall back to the smallest candidate and accept pagination growth.
    """
    original_page_count = len(doc.pages)
    chosen_base = _SIZE_CANDIDATES[-1]
    for candidate in _SIZE_CANDIDATES:
        heading_candidate = candidate + (_HEADING_SIZE - _BASE_SIZE)
        pages_needed, _ = _render_document(None, doc, candidate, heading_candidate)
        if pages_needed <= original_page_count:
            chosen_base = candidate
            break

    chosen_heading = chosen_base + (_HEADING_SIZE - _BASE_SIZE)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_path))
    c.setTitle(title)
    _, overflowed_ids = _render_document(c, doc, chosen_base, chosen_heading)
    c.save()
    return out_path, overflowed_ids
