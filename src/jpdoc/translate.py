"""Phase 1b — glossary-locked Japanese -> English translation via local Ollama.

Design decisions for accuracy + token efficiency on a 3B model:
  1. Translate ONE BLOCK PER CALL for paragraph/heading/seal blocks. A 3B model
     cannot reliably split multi-segment responses; one call per block is more
     deterministic and the per-call overhead is small for bounded clause lengths.
  2. Glossary preamble is built ONCE (module-level cache) and sent on every call —
     total token cost is preamble + one clause, never a whole contract.
  3. Tables translate one call PER CELL, and per LINE within a multi-line
     cell — see _translate_cell_text for why (whole-row and whole-cell calls
     both broke down on real dense form tables).
  4. [?] / [UNREADABLE_KANJI] markers pass through untouched per glossary rules.
  5. Tier-B escalation hook: flagged blocks are reserved for the 12-14B model stub.
  6. temperature=0 — legal translation must be deterministic, not creative.
"""
from __future__ import annotations

import ollama

from . import tierb
from .config import OLLAMA_MODEL
from .glossary import preamble
from .schema import Block, BlockType, Document


def translate_document(doc: Document) -> Document:
    """Translate all blocks in-place; preserve Japanese in block.text_ja."""
    sys_prompt = preamble()  # cached after first call

    for pg in doc.pages:
        for b in pg.blocks:
            if b.type == BlockType.TABLE:
                _translate_table(b, sys_prompt)
            else:
                _translate_block(b, sys_prompt)

    return doc


def _translate_block(b: Block, sys_prompt: str) -> None:
    if b.needs_review and tierb.vlm_available():
        return  # reserved for Tier-B 12-14B model
    if not b.text.strip():
        return

    b.text_ja = b.text
    b.text = _call_ollama_single(sys_prompt, b.text)


_CELL_INSTRUCTION = (
    "The text below is one field from a form/table — a short label or value, "
    "not prose. Translate it as a short label or value of similar length to "
    "the source; do not expand it into a full sentence or list multiple synonyms."
)


def _translate_table(block: Block, sys_prompt: str) -> None:
    if not block.table:
        return
    block.text_ja = block.text
    translated_rows = [[_translate_cell_text(cell, sys_prompt) for cell in row] for row in block.table]
    block.table = translated_rows
    block.text = "\n".join("\t".join(r) for r in translated_rows)

    # block.cells carries the per-cell geometry used by the layout-preserving
    # PDF renderer (see JCT_Backend_v1/app/services/render_service.py); it must be
    # kept in sync or the export draws the original untranslated Japanese.
    if block.cells:
        for cell in block.cells:
            if 0 <= cell.row < len(translated_rows) and 0 <= cell.col < len(translated_rows[cell.row]):
                cell.text = translated_rows[cell.row][cell.col]


def _translate_cell_text(text: str, sys_prompt: str) -> str:
    """Translate one table cell, LINE BY LINE for multi-line cells.

    Dense form tables often pack several numbered sub-items (e.g. a wages
    clause with 7 items) into a single cell. Sending that whole blob as one
    call overwhelmed the 3B model — it would drop or garble content instead
    of translating all of it. The earlier whole-ROW approach (cells joined
    with " | ", split back after translation) had the same problem plus a
    second one: the split didn't always line up, leaking literal "|"
    characters into the output. Per-line calls match the granularity that
    already works reliably for paragraph blocks, and need no delimiter to
    parse back out.
    """
    if not text.strip():
        return text
    lines = text.split("\n")
    if len(lines) == 1:
        return _call_ollama_single(sys_prompt, text, instruction=_CELL_INSTRUCTION)
    return "\n".join(
        _call_ollama_single(sys_prompt, line, instruction=_CELL_INSTRUCTION) if line.strip() else line
        for line in lines
    )


def _call_ollama_single(sys_prompt: str, text: str, instruction: str | None = None) -> str:
    """Translate exactly one text segment; return the English string.

    `instruction`, when given, is a call-specific addition to the user message
    (e.g. "keep table cells short") — kept OUT of the shared system preamble
    so it can't bleed into unrelated calls (paragraph/clause translation used
    the same preamble and got measurably worse when this was a global rule).
    """
    prefix = f"{instruction}\n\n" if instruction else ""
    resp = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"{prefix}Translate to English:\n\n{text}"},
        ],
        options={"temperature": 0},
    )
    return resp["message"]["content"].strip()


# ---------------------------------------------------------------------------
# Kept for tests that import these helpers directly.
# ---------------------------------------------------------------------------

def _parse_numbered(raw: str, expected: int) -> list[str]:
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    result: list[str] = []
    for ln in lines:
        if ln and ln[0].isdigit():
            rest = ln.split(".", 1)[-1].strip() if "." in ln else ln.split(")", 1)[-1].strip()
            result.append(rest)
        else:
            result.append(ln)
    while len(result) < expected:
        result.append("[TRANSLATION_MISSING]")
    return result[:expected]


def _call_ollama(sys_prompt: str, texts: list[str]) -> list[str]:
    """Kept for backwards compatibility with mocked tests."""
    return [_call_ollama_single(sys_prompt, t) for t in texts]
