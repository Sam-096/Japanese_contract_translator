"""Stage orchestrator — ties ingest -> preprocess -> OCR -> intermediate JSON.

Content-hash caching (efficiency #7): if an identical input was already processed,
the cached intermediate JSON is reused and no OCR runs at all.
"""
from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from . import ingest
from .schema import Document, Page

console = Console()


def process(path: Path, cache_dir: Path) -> Document:
    path = Path(path)
    cache_dir.mkdir(parents=True, exist_ok=True)
    sha = ingest.sha256_of(path)
    cache_file = cache_dir / f"{sha}.json"

    if cache_file.exists():
        console.print(f"[green]cache hit[/] {path.name} ({sha[:12]})")
        return Document.model_validate_json(cache_file.read_text(encoding="utf-8"))

    kind = ingest.classify(path)
    console.print(f"[cyan]processing[/] {path.name} -> kind={kind}")

    if kind == "digital_pdf":
        doc, needs_ocr = ingest.load_pdf_text(path)
        if needs_ocr:  # only import the heavy OCR stack if a page actually needs it
            from . import ocr, preprocess, raster

            for pno in needs_ocr:  # image-only pages only, never the whole file
                console.print(f"  page {pno}: no text layer -> OCR")
                img = preprocess.clean(raster.pdf_page_to_bgr(path, pno))
                _replace_page(doc, pno, ocr.ocr_image(img, pno))

    elif kind == "scanned_pdf":
        from . import ocr, preprocess, raster
        from .config import RASTER_DPI

        doc = Document(source_path=str(path), sha256=sha, kind=kind)
        import fitz

        with fitz.open(path) as pdf:
            page_rects = [(p.rect.width, p.rect.height) for p in pdf]
        for pno in range(1, len(page_rects) + 1):
            console.print(f"  page {pno}/{len(page_rects)}: OCR")
            img = preprocess.clean(raster.pdf_page_to_bgr(path, pno))
            width, height = page_rects[pno - 1]
            doc.pages.append(
                Page(number=pno, width=width, height=height,
                     blocks=ocr.ocr_image(img, pno, dpi=RASTER_DPI))
            )

    else:  # single image — no inherent page geometry, so treat pixel dims as
        # the canvas size at the same assumed DPI used to scale OCR bboxes,
        # giving a physically reasonable page size for the rendered PDF.
        from . import ocr, preprocess, raster
        from .config import RASTER_DPI

        doc = Document(source_path=str(path), sha256=sha, kind=kind)
        img = preprocess.clean(raster.image_file_to_bgr(path))
        h_px, w_px = img.shape[:2]
        scale = 72.0 / RASTER_DPI
        doc.pages.append(
            Page(number=1, width=w_px * scale, height=h_px * scale,
                 blocks=ocr.ocr_image(img, 1, dpi=RASTER_DPI))
        )

    cache_file.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
    flagged = len(doc.flagged())
    console.print(f"[green]done[/] {path.name} — {flagged} block(s) flagged for review")
    return doc


def _replace_page(doc: Document, pno: int, blocks) -> None:
    for pg in doc.pages:
        if pg.number == pno:
            pg.blocks = blocks
            return
    doc.pages.append(Page(number=pno, blocks=blocks))
