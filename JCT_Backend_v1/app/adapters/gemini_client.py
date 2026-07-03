"""Gemini cloud adapter — a second Tier-B option alongside Groq
(app/adapters/groq_client.py), same call pattern and same public interface
(`name`, `translate_document`, `translate_blocks`) so `translate_service.py`
can select between them without any other code changing. Table cells are
batched via Gemini's JSON response mode for the same reason Groq batches
them (see groq_client.py's docstring) — the glossary system-prompt is large
enough that resending it per-cell burns through a free-tier rate limit fast.

Free-tier pacing: Google AI Studio's no-cost tier caps requests per minute
(15 RPM for gemini-1.5-flash at the time this was written). `_enforce_rate_limit`
is a simple thread-safe token-bucket-of-one: it blocks the calling thread
until at least `60 / max_rpm` seconds have elapsed since the last call
started, class-level so it holds across every GeminiTranslator instance in
the process (translate_service.py may construct more than one during a
single translate_document + escalation pass).

Every call goes through app.core.cache first — same reasoning as Groq:
identical form labels and boilerplate clauses recur across documents and
across providers (the cache key is the source text hash, not provider-scoped),
so a Groq-primed cache entry is reused here too, and vice versa.

Batch instruction wording, the liability/negative-verb guardrails, and
markdown-fence-stripping are shared with groq_client.py via prompts.py.
Gemini in particular is prone to trying to "heal" a batch of isolated
table-cell fragments into more natural-sounding prose — blending two
adjacent cells' meaning together, or dropping the layout-carrying
punctuation a cell needs (e.g. '（有・無）') — when it infers they're part of
one semantic table. Strict `response_mime_type="application/json"` plus the
explicit "NO ROW BLEEDING"/"GRID SYMBOL PRESERVATION" rules in
prompts.BATCH_INSTRUCTION constrain it back to a flat, isolated
key->translation mapping. temperature=0.0 (not the SDK default) for the same
determinism reason Groq's calls use temperature=0.
"""
from __future__ import annotations

import json
import threading
import time

from jpdoc.glossary import preamble
from jpdoc.schema import Block, BlockType, Document

from app.adapters.prompts import (
    BATCH_INSTRUCTION,
    CELL_INSTRUCTION,
    LEGAL_GUARDRAILS,
    is_capacity_error,
    strip_json_fences,
)
from app.core import cache
from app.core.config import get_settings
from app.core.exceptions import AppError, GeminiRateLimitedError

_BATCH_CHUNK_SIZE = 40


class _RateLimiter:
    """Thread-safe pacing lock, class-level so it's shared across every
    GeminiTranslator instance in this process (see module docstring).
    """

    _lock = threading.Lock()
    _last_call_time = 0.0

    @classmethod
    def wait(cls, min_interval_s: float) -> None:
        with cls._lock:
            elapsed = time.time() - cls._last_call_time
            if elapsed < min_interval_s:
                time.sleep(min_interval_s - elapsed)
            cls._last_call_time = time.time()


class GeminiTranslator:
    name = "gemini"

    def __init__(self, model: str | None = None):
        settings = get_settings()
        if not settings.gemini_configured:
            raise AppError("Gemini API key not configured.")

        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)
        self._genai = genai
        self._model_name = model or settings.gemini_model
        self._min_interval_s = 60.0 / max(settings.gemini_max_requests_per_minute, 1.0)

    def translate_document(self, doc: Document, force_refresh: bool = False) -> Document:
        sys_prompt = f"{preamble()}\n\n{LEGAL_GUARDRAILS}"
        for pg in doc.pages:
            for b in pg.blocks:
                if b.type == BlockType.TABLE:
                    self._translate_table(b, sys_prompt, force_refresh=force_refresh)
                else:
                    self._translate_block(b, sys_prompt, force_refresh=force_refresh)
        return doc

    def translate_blocks(self, blocks: list[Block], force_refresh: bool = False) -> None:
        sys_prompt = f"{preamble()}\n\n{LEGAL_GUARDRAILS}"
        for b in blocks:
            if b.type == BlockType.TABLE:
                self._translate_table(b, sys_prompt, force_refresh=force_refresh)
            else:
                self._translate_block(b, sys_prompt, force_refresh=force_refresh)

    def _translate_block(self, b: Block, sys_prompt: str, force_refresh: bool = False) -> None:
        if not b.text.strip():
            return
        b.text_ja = b.text
        b.text = self._call(sys_prompt, b.text, force_refresh=force_refresh)

    def _translate_table(self, block: Block, sys_prompt: str, force_refresh: bool = False) -> None:
        if not block.table:
            return
        block.text_ja = block.text

        items: dict[str, str] = {}
        for r, row in enumerate(block.table):
            for c, cell in enumerate(row):
                if cell.strip():
                    items[f"{r}-{c}"] = cell

        translations: dict[str, str] = {}
        to_translate: dict[str, str] = {}
        for key, text in items.items():
            cached = cache.get_cached(text, force_refresh=force_refresh)
            if cached is not None:
                translations[key] = cached
            else:
                to_translate[key] = text

        if to_translate:
            fresh = self._translate_batch(to_translate, sys_prompt, force_refresh=force_refresh)
            translations.update(fresh)
            for key, text in to_translate.items():
                if key in fresh:
                    cache.set_cached(text, fresh[key], self.name)

        translated_rows = [
            [translations.get(f"{r}-{c}", cell) for c, cell in enumerate(row)]
            for r, row in enumerate(block.table)
        ]
        block.table = translated_rows
        block.text = "\n".join("\t".join(r) for r in translated_rows)

        if block.cells:
            for cell in block.cells:
                if 0 <= cell.row < len(translated_rows) and 0 <= cell.col < len(translated_rows[cell.row]):
                    cell.text = translated_rows[cell.row][cell.col]

    def _translate_batch(
        self, items: dict[str, str], sys_prompt: str, force_refresh: bool = False
    ) -> dict[str, str]:
        result: dict[str, str] = {}
        keys = list(items.keys())
        for start in range(0, len(keys), _BATCH_CHUNK_SIZE):
            chunk = {k: items[k] for k in keys[start:start + _BATCH_CHUNK_SIZE]}
            result.update(self._translate_batch_chunk(chunk, sys_prompt))

        for key, text in items.items():
            if key not in result or not str(result[key]).strip():
                result[key] = self._call(
                    sys_prompt, text, instruction=CELL_INSTRUCTION, force_refresh=force_refresh
                )
        return {k: str(v) for k, v in result.items()}

    def _translate_batch_chunk(self, items: dict[str, str], sys_prompt: str) -> dict[str, str]:
        user_content = f"{BATCH_INSTRUCTION}\n\n{json.dumps(items, ensure_ascii=False)}"
        try:
            model = self._genai.GenerativeModel(
                model_name=self._model_name,
                system_instruction=sys_prompt,
                generation_config=self._genai.types.GenerationConfig(
                    temperature=0.0, top_p=0.95, max_output_tokens=4096,
                    response_mime_type="application/json",
                ),
            )
            _RateLimiter.wait(self._min_interval_s)
            resp = model.generate_content(user_content)
            raw = strip_json_fences(resp.text or "{}")
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
        except Exception as exc:
            if is_capacity_error(exc):
                raise GeminiRateLimitedError(f"Gemini capacity error: {exc}") from exc
            raise AppError(f"Gemini translation call failed: {exc}") from exc

    def _call(
        self, sys_prompt: str, text: str, instruction: str | None = None, force_refresh: bool = False
    ) -> str:
        cached = cache.get_cached(text, force_refresh=force_refresh)
        if cached is not None:
            return cached

        prefix = f"{instruction}\n\n" if instruction else ""
        try:
            model = self._genai.GenerativeModel(
                model_name=self._model_name,
                system_instruction=sys_prompt,
                generation_config=self._genai.types.GenerationConfig(
                    temperature=0.0, top_p=0.95, max_output_tokens=1024,
                ),
            )
            _RateLimiter.wait(self._min_interval_s)
            resp = model.generate_content(f"{prefix}Translate to English:\n\n{text}")
            result = (resp.text or "").strip()
        except Exception as exc:
            if is_capacity_error(exc):
                raise GeminiRateLimitedError(f"Gemini capacity error: {exc}") from exc
            raise AppError(f"Gemini translation call failed: {exc}") from exc

        cache.set_cached(text, result, self.name)
        return result

