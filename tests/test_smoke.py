"""Lightweight smoke tests — schema + digital-PDF path only (no model weights).

These run WITHOUT downloading OCR models, so they're CI- and laptop-friendly.
"""
from pathlib import Path

import fitz

from jpdoc import ingest, render
from jpdoc.schema import Block, BlockType, Document, Page, Source


def test_schema_roundtrip():
    doc = Document(source_path="x", sha256="abc", kind="image")
    doc.pages.append(Page(number=1, blocks=[
        Block(id="p1-b00", page=1, text="甲は乙に支払う", confidence=0.5, needs_review=True),
        Block(id="p1-b01", page=1, text="第一条", type=BlockType.HEADING),
    ]))
    js = doc.model_dump_json()
    back = Document.model_validate_json(js)
    assert back.pages[0].blocks[0].text == "甲は乙に支払う"
    assert len(back.flagged()) == 1


def test_digital_pdf_path(tmp_path: Path):
    # build a tiny digital PDF with a real text layer
    pdf = tmp_path / "sample.pdf"
    d = fitz.open()
    pg = d.new_page()
    pg.insert_text((72, 72), "本契約は甲と乙の間で締結される。", fontsize=14)
    d.save(pdf); d.close()

    kind = ingest.classify(pdf)
    assert kind == "digital_pdf"
    doc, needs_ocr = ingest.load_pdf_text(pdf)
    assert doc.pages and doc.pages[0].blocks
    assert doc.pages[0].blocks[0].source == Source.PDF_TEXT
    assert needs_ocr == []  # text layer present → no OCR needed

    paths = render.write_transcription(doc, tmp_path / "out", "sample")
    assert paths["ja_md"].exists() and paths["json"].exists()
