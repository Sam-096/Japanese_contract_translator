"""Compiles a translated `DocumentCanvas` into an absolutely-positioned
HTML/CSS page and renders it to PDF via WeasyPrint.

Font-fit strategy
-------------------
English is routinely ~30% longer than the source Japanese for the same
meaning, but the bounding box for each block is fixed (it came from the
original document's layout). `fit_font_size` estimates whether the
translated string will wrap to more lines than the box's height allows at
the original font size, and if so shrinks the font in small steps — down to
a floor (`min_scale`, default 60% of the original) — rather than letting
text silently overflow its box. The estimate is a heuristic (average
character width as a fraction of font size, not real glyph metrics), so it
intentionally leaves headroom rather than fitting exactly to the pixel; a
block that still can't fit at the floor scale is reported as overflowed so
the caller can decide how to handle it (flag for review, allow overflow,
expand the box) instead of that decision being made silently here.
"""
from __future__ import annotations

import html
from dataclasses import dataclass

from .schema import DocumentCanvas, TextBlock

_AVG_CHAR_WIDTH_RATIO = 0.55  # average glyph width as a fraction of font-size, for proportional Latin text
_LINE_HEIGHT_RATIO = 1.2
_MIN_SCALE = 0.6
_SCALE_STEP = 0.05

_FONT_STYLE_CSS = {
    "normal": "font-weight: normal; font-style: normal;",
    "bold": "font-weight: bold; font-style: normal;",
    "italic": "font-weight: normal; font-style: italic;",
    "bold_italic": "font-weight: bold; font-style: italic;",
}


@dataclass
class FitResult:
    font_size: float
    overflowed: bool


def _estimate_lines(text: str, box_width_pt: float, font_size: float) -> int:
    if not text:
        return 1
    chars_per_line = max(1, int(box_width_pt / (font_size * _AVG_CHAR_WIDTH_RATIO)))
    lines = 0
    for paragraph in text.split("\n"):
        lines += max(1, -(-len(paragraph) // chars_per_line))  # ceil div
    return max(1, lines)


def fit_font_size(
    text: str,
    box_width_pt: float,
    box_height_pt: float,
    base_font_size: float,
    min_scale: float = _MIN_SCALE,
    step: float = _SCALE_STEP,
) -> FitResult:
    """Search downward from `base_font_size` for the largest size at which
    `text` is estimated to fit `box_height_pt` (given wrapping constrained
    by `box_width_pt`). Returns the floor size with `overflowed=True` if
    nothing in [min_scale, 1.0] fits.
    """
    scale = 1.0
    chosen = base_font_size
    fits = False
    while scale >= min_scale - 1e-9:
        candidate = base_font_size * scale
        lines = _estimate_lines(text, box_width_pt, candidate)
        if lines * candidate * _LINE_HEIGHT_RATIO <= box_height_pt:
            chosen = candidate
            fits = True
            break
        chosen = candidate
        scale -= step
    return FitResult(font_size=chosen, overflowed=not fits)


def _block_to_div(block: TextBlock, page_width_pt: float, page_height_pt: float) -> str:
    x0, y0, x1, y1 = block.bounding_box.to_points(page_width_pt, page_height_pt)
    width_pt, height_pt = x1 - x0, y1 - y0

    display_text = block.translated_text if block.translated_text is not None else block.raw_text
    fit = fit_font_size(display_text, width_pt, height_pt, block.font_size)

    style_css = _FONT_STYLE_CSS.get(block.font_style.value if hasattr(block.font_style, "value") else block.font_style, "")
    overflow_class = " overflow-flag" if fit.overflowed else ""

    escaped = html.escape(display_text).replace("\n", "<br/>")
    return (
        f'<div class="text-block{overflow_class}" data-block-id="{html.escape(block.id)}" '
        f'style="left:{x0:.2f}pt; top:{y0:.2f}pt; width:{width_pt:.2f}pt; height:{height_pt:.2f}pt; '
        f'font-size:{fit.font_size:.2f}pt; {style_css}">{escaped}</div>'
    )


_PAGE_CSS = """
@page { margin: 0; }
body { margin: 0; padding: 0; }
.page {
    position: relative;
    overflow: hidden;
    background-repeat: no-repeat;
    background-size: 100% 100%;
}
.text-block {
    position: absolute;
    line-height: 1.2;
    white-space: pre-wrap;
    overflow-wrap: break-word;
    font-family: "Noto Sans JP", "Noto Sans", sans-serif;
}
.text-block.overflow-flag { outline: 1px dashed red; }
"""


def render_canvas_to_html(canvas: DocumentCanvas) -> str:
    """Build a standalone HTML document for one page. `canvas.blocks`
    should already have `translated_text` populated (falls back to
    `raw_text` per-block otherwise, so an un-translated canvas still
    renders for layout debugging).
    """
    bg_css = ""
    if canvas.background_svg_path:
        bg_css = f'background-image: url("{html.escape(canvas.background_svg_path)}");'

    blocks_html = "\n".join(
        _block_to_div(b, canvas.width_pt, canvas.height_pt) for b in canvas.blocks
    )

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>{_PAGE_CSS}</style>
</head>
<body>
<div class="page" style="width:{canvas.width_pt:.2f}pt; height:{canvas.height_pt:.2f}pt; {bg_css}">
{blocks_html}
</div>
</body>
</html>"""


def compile_html_to_pdf(html_str: str, out_path: str) -> None:
    """Render an HTML string to a PDF file via WeasyPrint.

    Known Windows gap: WeasyPrint's text shaping depends on native
    Pango/GObject libraries (`libgobject-2.0-0` etc.) that aren't part of
    a normal Windows Python install — `pip install weasyprint` alone is not
    enough. On a machine without the GTK3 runtime installed, this raises
    `OSError: cannot load library 'libgobject-2.0-0'` at the `from
    weasyprint import HTML` line, before any of this module's own logic
    runs (verified: `render_canvas_to_html` itself was smoke-tested and
    confirmed correct independent of this call). Fix by installing the
    GTK3 Runtime for Windows (see WeasyPrint's own install docs), or run
    this on Linux/macOS/Docker where the system package manager provides
    Pango directly and no extra step is needed.
    """
    from weasyprint import HTML

    HTML(string=html_str).write_pdf(out_path)
