"""Phase-1b translation policy (development.md §7):

- Dense form/table documents (any real table detected — see `_has_table_blocks`)
  use the configured cloud provider (Groq or Gemini — see `_cloud_translator`)
  as the PRIMARY translator when one is configured. Real-document testing
  showed the local 3B model is measurably less reliable on dense bordered
  forms (label/value tables with many short fields): confirmed bugs aside,
  it produces plausible-looking but wrong output on tricky short labels
  (e.g. mistranslating 休日 as "Weekend" rather than "Holidays", or garbling
  退職に関する事項 entirely) — including proven run-to-run non-determinism on
  the exact same input even at temperature=0. Prose-only contracts (no
  detected tables) keep the local-first policy — it's measurably reliable
  there and free.
- Otherwise: local Ollama (qwen2.5:3b) translates the whole document — zero
  cloud cost. If local Ollama is unreachable (e.g. cloud deployment with no
  local daemon) and a cloud provider is configured, it translates the whole
  document instead. If both are available, low-confidence/flagged blocks are
  re-translated via the cloud provider as a Tier-B escalation
  (paragraph/heading/list/seal only — table cells are not escalated because
  the local pass overwrites the original table text in place, so there's no
  clean JA source left to resend).

Provider selection: `settings.cloud_provider` ("groq" or "gemini", set via
JCT_LLM_PROVIDER) picks which cloud adapter `_cloud_translator()` builds by
default. Both adapters share the same interface (`name`, `translate_document`,
`translate_blocks`) and both go through the same Redis/Postgres translation
cache, so switching providers doesn't lose cache hits already recorded by
the other one — the cache key is the source text hash, not provider-scoped.

Automatic provider fallback: if the configured provider raises a
ProviderCapacityError (429 rate limit, 503 unavailable — see
core/exceptions.py and adapters/prompts.is_capacity_error), and the OTHER
cloud provider is also configured, `_translate_document_with_fallback`/
`_translate_blocks_with_fallback` transparently retry with it — the job
just takes a bit longer, the caller never sees an error. Whole-document
retries start from a clean pre-translation deep copy rather than the
partially-mutated in-progress one: a table can fail mid-batch with some
cells already translated in place, and there's no cheap way to tell which;
starting clean avoids re-translating already-English text. This isn't
wasted work, because whatever the first provider already completed (and
cached) before failing comes back as free cache hits on the retry.
"""
from __future__ import annotations

import logging

from jpdoc.schema import Block, BlockType, Document

from app.adapters.gemini_client import GeminiTranslator
from app.adapters.groq_client import GroqTranslator
from app.adapters.local_llm_client import LocalOllamaTranslator
from app.core.config import get_settings
from app.core.exceptions import ProviderCapacityError, TranslationUnavailableError
from app.services import document_store

logger = logging.getLogger("app.translate_service")


def _has_table_blocks(doc: Document) -> bool:
    return any(b.type == BlockType.TABLE for pg in doc.pages for b in pg.blocks)


def _cloud_translator(provider: str | None = None):
    provider = provider or get_settings().cloud_provider
    if provider == "gemini":
        return GeminiTranslator()
    return GroqTranslator()


def _fallback_provider(provider: str) -> str | None:
    """The other cloud provider, if it's actually configured — None if
    there's nothing to fall back to (only one provider set up)."""
    settings = get_settings()
    if provider == "gemini" and settings.groq_configured:
        return "groq"
    if provider == "groq" and settings.gemini_configured:
        return "gemini"
    return None


def _notify_fallback(provider: str, fallback_provider: str, exc: Exception, job_id: str | None) -> None:
    from app.core import notifications
    from app.services import job_service

    if job_id:
        job_service.set_status(
            job_id, "translating", "Optimizing translation pipeline — switching to backup engine"
        )
    notifications.send_slack_alert(
        severity="warning",
        title=f"Translation provider fallback: {provider} -> {fallback_provider}",
        detail=str(exc),
        job_id=job_id,
    )


def _translate_document_with_fallback(
    doc: Document, force_refresh: bool, job_id: str | None = None
) -> tuple[Document, str]:
    settings = get_settings()
    provider = settings.cloud_provider
    original = doc.model_copy(deep=True)
    translator = _cloud_translator(provider)
    try:
        translator.translate_document(doc, force_refresh=force_refresh)
        return doc, translator.name
    except ProviderCapacityError as exc:
        fallback_provider = _fallback_provider(provider)
        if fallback_provider is None:
            raise
        logger.warning("%s unavailable (%s) — falling back to %s", provider, exc, fallback_provider)
        _notify_fallback(provider, fallback_provider, exc, job_id)
        doc = original.model_copy(deep=True)
        fallback = _cloud_translator(fallback_provider)
        fallback.translate_document(doc, force_refresh=force_refresh)
        return doc, fallback.name


def _translate_blocks_with_fallback(
    blocks: list[Block], force_refresh: bool, job_id: str | None = None
) -> str:
    settings = get_settings()
    provider = settings.cloud_provider
    originals = [(b, b.text) for b in blocks]
    translator = _cloud_translator(provider)
    try:
        translator.translate_blocks(blocks, force_refresh=force_refresh)
        return translator.name
    except ProviderCapacityError as exc:
        fallback_provider = _fallback_provider(provider)
        if fallback_provider is None:
            raise
        logger.warning("%s unavailable (%s) — falling back to %s", provider, exc, fallback_provider)
        _notify_fallback(provider, fallback_provider, exc, job_id)
        for b, ja_text in originals:
            b.text = ja_text
        fallback = _cloud_translator(fallback_provider)
        fallback.translate_blocks(blocks, force_refresh=force_refresh)
        return fallback.name


def run_translate(document_id: str, force_refresh: bool = False, job_id: str | None = None) -> dict[str, str]:
    """`force_refresh` bypasses the translation cache for this run only (see
    app.core.cache) — every cloud call re-translates from scratch and
    overwrites the stale cache entry with the fresh result. Local Ollama
    translation is unaffected since it was never cached (see cache.py's
    docstring: no per-call cost/rate-limit pressure there).

    `job_id`, when given, lets a provider fallback (see module docstring)
    post a friendly in-progress message to the job the caller is polling,
    instead of the switch happening invisibly. Optional because this
    function is also usable standalone (e.g. tests, CLI) without a job."""
    record = document_store.get(document_id)
    if record is None or record.document is None:
        raise ValueError(f"Document {document_id} has not been ingested yet")
    doc = record.document
    settings = get_settings()

    if settings.cloud_configured and _has_table_blocks(doc):
        doc, translator_name = _translate_document_with_fallback(doc, force_refresh, job_id)
        translator_map = {b.id: translator_name for pg in doc.pages for b in pg.blocks}
        document_store.update(
            document_id, document=doc, translated=True, translator_map=translator_map
        )
        return translator_map

    translator_map = {}
    local_ok = True
    try:
        local = LocalOllamaTranslator()
        local.translate_document(doc)
        translator_map = {b.id: local.name for pg in doc.pages for b in pg.blocks}
    except Exception:
        local_ok = False
        if not settings.cloud_configured:
            raise TranslationUnavailableError(
                "Local Ollama is unavailable and no cloud fallback (Groq/Gemini) is configured."
            )

    if not local_ok and settings.cloud_configured:
        doc, translator_name = _translate_document_with_fallback(doc, force_refresh, job_id)
        translator_map = {b.id: translator_name for pg in doc.pages for b in pg.blocks}
    elif local_ok and settings.cloud_configured:
        escalate = [
            b
            for pg in doc.pages
            for b in pg.blocks
            if b.needs_review and b.type != BlockType.TABLE
        ]
        if escalate:
            for b in escalate:
                b.text = b.text_ja or b.text  # restore JA source before re-translating
            translator_name = _translate_blocks_with_fallback(escalate, force_refresh, job_id)
            for b in escalate:
                translator_map[b.id] = translator_name

    document_store.update(
        document_id, document=doc, translated=True, translator_map=translator_map
    )
    return translator_map
