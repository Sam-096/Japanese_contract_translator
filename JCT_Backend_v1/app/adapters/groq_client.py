"""Groq cloud adapter — Tier-B translation/escalation.

Mirrors the call pattern in jpdoc.translate (one block per call, glossary preamble
as system prompt, temperature=0) but targets the Groq-hosted model instead of the
local Ollama daemon. Used to: (a) translate everything when local Ollama is
unavailable (e.g. cloud deployment with no local model), and (b) re-translate
flagged/low-confidence blocks as a Tier-B escalation when both are available.

Table cells are translated in BATCHES (one JSON-mode call per table, not one
call per cell) — see `_translate_batch`. A per-cell/per-line design was tried
first to fix a local-3B-specific accuracy problem (see jpdoc.translate), but
Groq's free tier caps at 12,000 tokens/minute and the ~700-token glossary
system prompt was being resent in full on every single cell/line call —
confirmed via real usage logs hitting 429 rate_limit_exceeded repeatedly on
one dense form table. Groq's 70B model handles a whole multi-line cell (or a
whole batch of cells) coherently in one call, unlike the local 3B model, so
batching doesn't reintroduce the accuracy problem it was designed to avoid.

Every call also goes through app.core.cache first (Redis, backed by the
Postgres translation_cache table) — form labels and boilerplate clauses recur
constantly across different documents (e.g. 契約期間 -> "Contract Period" in
nearly every employment contract), so a repeat is a cache hit, not a fresh
API call. Caching degrades silently to "always translate" if neither Redis
nor Postgres is configured.

Batch instruction wording and the liability/negative-verb guardrails are
shared with gemini_client.py via prompts.py, so both providers are held to
the same structural-preservation bar and don't silently drift apart.
"""
from __future__ import annotations

import json

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
from app.core.exceptions import AppError, GroqRateLimitedError

_REQUEST_TIMEOUT_S = 30
_BATCH_CHUNK_SIZE = 40  # safety cap so one request can't balloon on a huge table


class GroqTranslator:
    name = "groq"

    def __init__(self, model: str | None = None):
        settings = get_settings()
        if not settings.groq_configured:
            raise AppError("Groq API key not configured.")

        from groq import Groq

        self._client = Groq(api_key=settings.groq_api_key, timeout=_REQUEST_TIMEOUT_S)
        self._model = model or settings.groq_model

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

        # Keep block.cells (per-cell geometry used by render_service) in sync —
        # otherwise the layout-preserving PDF export draws the stale,
        # pre-translation Japanese instead of what was just translated here.
        if block.cells:
            for cell in block.cells:
                if 0 <= cell.row < len(translated_rows) and 0 <= cell.col < len(translated_rows[cell.row]):
                    cell.text = translated_rows[cell.row][cell.col]

    def _translate_batch(
        self, items: dict[str, str], sys_prompt: str, force_refresh: bool = False
    ) -> dict[str, str]:
        """Translate many short form-field texts in ONE call via JSON mode.
        Falls back to an individual call for any id the batch response is
        missing (bad JSON, dropped id) rather than silently leaving Japanese.
        """
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
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
            raw = strip_json_fences(resp.choices[0].message.content or "{}")
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
        except Exception as exc:  # Groq SDK exception types vary by version
            if is_capacity_error(exc):
                raise GroqRateLimitedError(f"Groq capacity error: {exc}") from exc
            raise AppError(f"Groq translation call failed: {exc}") from exc

    def _call(
        self, sys_prompt: str, text: str, instruction: str | None = None, force_refresh: bool = False
    ) -> str:
        cached = cache.get_cached(text, force_refresh=force_refresh)
        if cached is not None:
            return cached

        prefix = f"{instruction}\n\n" if instruction else ""
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": f"{prefix}Translate to English:\n\n{text}"},
                ],
                temperature=0,
            )
            result = (resp.choices[0].message.content or "").strip()
        except Exception as exc:  # Groq SDK exception types vary by version
            if is_capacity_error(exc):
                raise GroqRateLimitedError(f"Groq capacity error: {exc}") from exc
            raise AppError(f"Groq translation call failed: {exc}") from exc

        cache.set_cached(text, result, self.name)
        return result
