"""Tunable thresholds. Conservative defaults: favour accuracy, flag uncertainty."""
from __future__ import annotations

# A line/block below this OCR confidence is escalated (manga-ocr) or flagged [?].
CONFIDENCE_THRESHOLD: float = 0.80

# If a digital PDF page yields fewer than this many characters from its text
# layer, treat the page as effectively image-only and route it to OCR.
MIN_PDF_CHARS_PER_PAGE: int = 8

# DPI used when rasterising scanned/empty PDF pages for OCR.
RASTER_DPI: int = 300

# Marker injected for unrecoverable content (adopted from the external plan).
UNREADABLE = "[UNREADABLE_KANJI]"
LOWCONF = "[?]"

# Ollama model for Tier-A translation (Phase 1b). One model resident at a time.
OLLAMA_MODEL = "qwen2.5:3b-instruct"
