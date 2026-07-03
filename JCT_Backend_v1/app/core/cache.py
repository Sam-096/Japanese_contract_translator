"""Translation cache: Redis is the hot path (near-zero latency, avoids the API
call entirely), the `translation_cache` Postgres table is the durable backing
store so the cache survives a Redis restart/eviction and gives an audit trail.

Keyed by sha256 of the source text — form labels and boilerplate clauses recur
constantly across different documents (e.g. 契約期間 -> "Contract Period" in
nearly every employment contract), so this turns repeat translations into a
cache hit instead of a fresh API call. Only wired into the Groq adapter (see
adapters/groq_client.py) — that's the path with real per-call token cost and
rate-limit pressure; local Ollama has neither, so it isn't worth the added
complexity there.

Every function degrades gracefully when Redis/Postgres aren't configured or
are temporarily unreachable: caching is an optimization, never a hard
dependency for translation to work.

Cache-bypass for development: a stale cache hit under active prompt
iteration silently serves output from the OLD prompt, which looks
indistinguishable from a real translation and makes prompt changes appear
to do nothing. Two ways to force a miss (both skip the READ only — a write
still happens afterward, so the stale entry gets overwritten with the
fresh result rather than left dangling):
  - `DEV_MODE=true` (settings.dev_mode): every get_cached() call misses,
    for the life of the process.
  - `get_cached(text, force_refresh=True)`: one call misses, e.g. wired
    to a `?force_refresh=true` query param on a specific request.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

from app.core.config import get_settings

logger = logging.getLogger("app.cache")

_CACHE_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days
_KEY_PREFIX = "jpdoc:tcache:"

_redis_client = None


def _get_redis():
    global _redis_client
    settings = get_settings()
    if not settings.redis_configured:
        return None
    if _redis_client is None:
        import redis

        _redis_client = redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=3)
    return _redis_client


def hash_text(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def get_cached(text: str, *, force_refresh: bool = False) -> str | None:
    """Return a cached translation for `text`, or None on a cache miss (or if
    neither Redis nor Postgres is configured/reachable), or if a cache bypass
    is active — see module docstring for DEV_MODE / force_refresh."""
    text = text.strip()
    if not text:
        return None
    source_hash = hash_text(text)

    settings = get_settings()
    if force_refresh or settings.dev_mode:
        logger.info(
            "cache bypass (%s) for %s — forcing fresh translation",
            "force_refresh" if force_refresh else "DEV_MODE",
            source_hash[:12],
        )
        return None

    r = _get_redis()
    if r is not None:
        try:
            cached = r.get(_KEY_PREFIX + source_hash)
            if cached is not None:
                return cached
        except Exception:
            pass  # Redis hiccup — fall through to Postgres, never fail the call

    if not settings.database_configured:
        return None

    from app.core.db import get_conn

    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT translated_text FROM translation_cache WHERE source_hash = %s",
                (source_hash,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            translated = row[0]
            cur.execute(
                "UPDATE translation_cache SET hit_count = hit_count + 1, last_used_at = %s "
                "WHERE source_hash = %s",
                (datetime.now(timezone.utc), source_hash),
            )
            conn.commit()
    except Exception:
        return None

    if r is not None:
        try:
            r.setex(_KEY_PREFIX + source_hash, _CACHE_TTL_SECONDS, translated)
        except Exception:
            pass
    return translated


def set_cached(text: str, translated: str, translator: str) -> None:
    text = text.strip()
    if not text or not translated.strip():
        return
    source_hash = hash_text(text)

    r = _get_redis()
    if r is not None:
        try:
            r.setex(_KEY_PREFIX + source_hash, _CACHE_TTL_SECONDS, translated)
        except Exception:
            pass

    settings = get_settings()
    if not settings.database_configured:
        return

    from app.core.db import get_conn

    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO translation_cache (source_hash, source_text, translated_text, translator)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (source_hash) DO UPDATE
                    SET translated_text = EXCLUDED.translated_text,
                        translator = EXCLUDED.translator,
                        last_used_at = now()
                """,
                (source_hash, text, translated, translator),
            )
            conn.commit()
    except Exception:
        pass
