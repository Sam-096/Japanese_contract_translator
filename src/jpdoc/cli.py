"""CLI entrypoint — Phase 1a + 1b.

    python -m jpdoc.cli <input.pdf|image>                   # transcription only (1a)
    python -m jpdoc.cli <input.pdf|image> --translate        # + English output (1b)

Outputs (1a):  <stem>.ja.md, <stem>.intermediate.json, <stem>.review.md (if flags)
Outputs (1b): adds <stem>.en.md, <stem>.bilingual.md

All output goes to --out/<stem>/. Cache lives in --cache/ (content-hash keyed).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Windows consoles default to cp1252; force UTF-8 so JP text prints correctly.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from rich.console import Console

from . import pipeline, render

console = Console()


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="jpdoc",
        description="Reliable Japanese document -> searchable English (local, offline)",
    )
    ap.add_argument("input", type=Path, help="PDF or image file")
    ap.add_argument("--out", type=Path, default=Path("output"), help="Output directory")
    ap.add_argument("--cache", type=Path, default=Path(".cache"), help="Cache directory")
    ap.add_argument(
        "--translate", action="store_true",
        help="Run Phase 1b: translate to English and write .en.md / .bilingual.md",
    )
    args = ap.parse_args()

    if not args.input.exists():
        console.print(f"[red]not found:[/] {args.input}")
        return 2

    # Phase 1a — ingest + OCR + intermediate JSON
    doc = pipeline.process(args.input, args.cache)
    stem = args.input.stem
    out_dir = args.out / stem
    paths = render.write_transcription(doc, out_dir, stem)

    # Phase 1b — translate (optional)
    if args.translate:
        console.print("[cyan]translating[/] (offline, via local Ollama)")
        from .translate import translate_document
        doc = translate_document(doc)
        paths.update(render.write_english(doc, out_dir, stem))

    console.print("[bold green]written:[/]")
    for k, p in paths.items():
        console.print(f"  {k}: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
