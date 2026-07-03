"""Stage 6 — render the searchable output files from the intermediate Document.

Phase 1a writes the Japanese transcription + the audit JSON. The English files are
produced in Phase 1b (translate.py) but the same renderer is reused.
"""
from __future__ import annotations

from pathlib import Path

from .schema import BlockType, Document


def _block_md(b) -> str:
    if b.type == BlockType.TABLE and b.table:
        rows = b.table
        if not rows:
            return ""
        head = "| " + " | ".join(rows[0]) + " |"
        sep = "| " + " | ".join("---" for _ in rows[0]) + " |"
        body = "\n".join("| " + " | ".join(r) + " |" for r in rows[1:])
        return f"{head}\n{sep}\n{body}".strip()
    if b.type == BlockType.HEADING:
        return f"## {b.text}"
    return b.text


def write_transcription(doc: Document, out_dir: Path, stem: str) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    # 1) Japanese transcription (searchable, structured)
    md: list[str] = [f"# {stem} — transcription (JA)\n"]
    for pg in doc.pages:
        md.append(f"\n<!-- page {pg.number} -->")
        for b in sorted(pg.blocks, key=lambda x: x.order):
            flag = "  [REVIEW]" if b.needs_review else ""
            md.append(_block_md(b) + flag)
    p = out_dir / f"{stem}.ja.md"
    p.write_text("\n\n".join(md), encoding="utf-8")
    paths["ja_md"] = p

    # 2) audit JSON (full provenance, confidence, bbox)
    pj = out_dir / f"{stem}.intermediate.json"
    pj.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
    paths["json"] = pj

    # 3) review file: only the flagged rows, for fast human patching
    flagged = doc.flagged()
    if flagged:
        rev = [f"# {stem} — {len(flagged)} item(s) need review\n",
               "| page | block | confidence | text |", "| --- | --- | --- | --- |"]
        for b in flagged:
            safe = b.text.replace("\n", " ").replace("|", "\\|")
            rev.append(f"| {b.page} | {b.id} | {b.confidence:.2f} | {safe} |")
        pr = out_dir / f"{stem}.review.md"
        pr.write_text("\n".join(rev), encoding="utf-8")
        paths["review"] = pr

    return paths


def write_english(doc: Document, out_dir: Path, stem: str) -> dict[str, Path]:
    """Write English output files after translate_document() has run.

    Produces:
      <stem>.en.md          — primary searchable English output
      <stem>.bilingual.md   — JP | EN side-by-side for human review
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    en_lines: list[str] = [f"# {stem} (English)\n"]
    bi_lines: list[str] = [f"# {stem} — bilingual review (JA | EN)\n",
                           "| # | Japanese | English |", "| --- | --- | --- |"]
    row = 0

    for pg in doc.pages:
        en_lines.append(f"\n<!-- page {pg.number} -->")
        for b in sorted(pg.blocks, key=lambda x: x.order):
            en_text = _block_md(b)
            en_lines.append(en_text + ("  [REVIEW]" if b.needs_review else ""))

            ja_text = getattr(b, "text_ja", b.text)  # set by translate.py
            row += 1
            safe_ja = ja_text.replace("\n", " ").replace("|", "\\|")
            safe_en = b.text.replace("\n", " ").replace("|", "\\|")
            flag = " [REVIEW]" if b.needs_review else ""
            bi_lines.append(f"| {row} | {safe_ja} | {safe_en}{flag} |")

    p_en = out_dir / f"{stem}.en.md"
    p_en.write_text("\n\n".join(en_lines), encoding="utf-8")
    paths["en_md"] = p_en

    p_bi = out_dir / f"{stem}.bilingual.md"
    p_bi.write_text("\n".join(bi_lines), encoding="utf-8")
    paths["bilingual_md"] = p_bi

    return paths
