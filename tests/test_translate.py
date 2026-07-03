"""Phase 1b unit tests — mock Ollama so no model is needed in CI."""
from __future__ import annotations

from unittest.mock import patch

from jpdoc.glossary import preamble
from jpdoc.schema import Block, BlockType, Document, Page
from jpdoc.translate import _parse_numbered, translate_document


def test_preamble_contains_key_terms():
    p = preamble()
    assert "Party A" in p
    assert "joint and several guarantee" in p
    assert "automatic renewal" in p
    assert preamble() is preamble()  # cached


def test_parse_numbered_happy_path():
    raw = "1. Article 1\n2. Party A shall pay Party B."
    assert _parse_numbered(raw, 2) == ["Article 1", "Party A shall pay Party B."]


def test_parse_numbered_pads_missing():
    result = _parse_numbered("1. Only one line", 3)
    assert len(result) == 3
    assert result[1] == "[TRANSLATION_MISSING]"


def _make_doc() -> Document:
    doc = Document(source_path="x", sha256="abc", kind="digital_pdf")
    doc.pages.append(Page(number=1, blocks=[
        Block(id="p1-b00", page=1, text="第一条 本契約は甲と乙の間で締結される。", order=0),
        Block(id="p1-b01", page=1, text="第二条 賃料は毎月末日までに支払う。", order=1),
    ]))
    return doc


def _fake_chat(model, messages, options=None):
    """Return canned English for each known Japanese input."""
    user_text = messages[-1]["content"]
    if "第一条" in user_text:
        content = "Article 1: This agreement is concluded between Party A and Party B."
    elif "第二条" in user_text:
        content = "Article 2: Rent shall be paid by the last day of each month."
    else:
        content = "Translation."
    return {"message": {"content": content}}


def test_translate_document_replaces_text():
    with patch("jpdoc.translate.ollama.chat", side_effect=_fake_chat):
        doc = translate_document(_make_doc())

    blocks = doc.pages[0].blocks
    assert "Party A" in blocks[0].text
    assert "Party B" in blocks[0].text
    assert "Rent" in blocks[1].text
    assert blocks[0].text_ja == "第一条 本契約は甲と乙の間で締結される。"


def test_translate_document_end_to_end_render(tmp_path):
    from jpdoc import render

    with patch("jpdoc.translate.ollama.chat", side_effect=_fake_chat):
        doc = translate_document(_make_doc())

    paths = render.write_english(doc, tmp_path, "test")
    en = paths["en_md"].read_text(encoding="utf-8")
    bi = paths["bilingual_md"].read_text(encoding="utf-8")

    assert "Party A" in en
    assert "Rent" in en
    assert "第一条" in bi
    assert "Party A" in bi
