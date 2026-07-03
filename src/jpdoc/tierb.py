"""Tier-B interface (GPU): VLM handwriting recovery + 12-14B reasoning.

On this laptop these are STUBS. They expose the exact call signature the real
GPU implementation will satisfy, so Tier-A code is already wired correctly. When
a GPU host is available, point JPDOC_TIERB_URL at it and swap these for HTTP calls.

Design intent: Tier B is invoked ONLY for flagged/low-confidence regions, never
whole pages — this is the central accuracy/efficiency trade-off.
"""
from __future__ import annotations

import os

TIERB_URL = os.environ.get("JPDOC_TIERB_URL", "")


def vlm_available() -> bool:
    return bool(TIERB_URL)


def recover_handwriting(image_crop_png: bytes) -> tuple[str, float]:
    """Return (recovered_text, confidence) for one low-confidence crop.

    Stub: signals 'not recovered' so the caller keeps the [UNREADABLE] flag.
    Real impl (GPU): POST the crop to Qwen2.5-VL-7B / PLaMo-2.1-VL with a prompt
    that suppresses watermark/seal noise and emits [UNREADABLE_KANJI] on failure.
    """
    if not vlm_available():
        return "", 0.0
    raise NotImplementedError("Wire Tier-B VLM endpoint via JPDOC_TIERB_URL")


def legal_translate(text: str, glossary_preamble: str) -> str:
    """Tier-B 12-14B legal translation (multi-pass audit). Stub until GPU.

    Real impl (GPU): Shisa V2.1 / ELYZA with the cached glossary preamble.
    """
    if not vlm_available():
        raise RuntimeError("Tier-B not configured; use Tier-A translate instead")
    raise NotImplementedError("Wire Tier-B reasoning endpoint via JPDOC_TIERB_URL")
