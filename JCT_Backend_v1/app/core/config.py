"""Settings loaded from JCT_Backend_v1/.env. See JCT_Backend_v1/.env.example for the full list."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_fallback_model: str = "llama-3.1-8b-instant"

    gemini_api_key: str = ""
    # "gemini-1.5-flash" (the model the original spec named) was retired by
    # Google — confirmed via a live ListModels call against a real key on
    # 2026-07-02, which 404'd on 1.5-flash but returned only 2.x/3.x models.
    # "-latest" is an alias Google keeps pointed at the current recommended
    # flash model, so this default won't silently 404 again next retirement.
    gemini_model: str = "gemini-flash-latest"
    # Free-tier RPM cap the pacing lock in adapters/gemini_client.py throttles to.
    gemini_max_requests_per_minute: float = 15.0

    # Which cloud provider translate_service.py's Tier-B/primary-for-tables
    # slot uses: "groq" or "gemini". Falls back to whichever of the two is
    # actually configured if the selected one isn't (see cloud_configured).
    # Env var is JCT_LLM_PROVIDER (not the auto-derived LLM_PROVIDER) to match
    # this project's JCT_* naming convention.
    llm_provider: str = Field(default="groq", validation_alias="JCT_LLM_PROVIDER")

    # Postgres (Supabase or any Postgres) — document/job persistence, see
    # JCT_Backend_v1/db/schema.sql. When unset, document_store/job_service fall back
    # to in-memory storage (Phase 1 behavior, single-process only).
    database_url: str = ""
    # Redis — translation cache (hash of source text -> translated text), see
    # app/core/cache.py. When unset, caching is skipped (always translate).
    redis_url: str = ""

    # When true, app.core.cache.get_cached() always misses (never reads Redis
    # or Postgres) so prompt/validation changes take effect immediately
    # without a stale cache entry masking them. Writes are NOT disabled — a
    # fresh translation still overwrites the old cache entry, so the cache
    # stays usable for anyone not in dev mode. See cache.py.
    dev_mode: bool = Field(default=False, validation_alias="DEV_MODE")

    # Slack incoming-webhook URL for developer error alerts — see
    # core/notifications.py and core/error_catalog.py. Unset = alerts are
    # skipped silently (never blocks the request/job they're reporting on).
    slack_webhook_url: str = ""

    # When true, /upload synchronously rejects scanned PDFs/raw images
    # (ScannedDocumentUnsupportedError) before a job is even created,
    # instead of letting the OCR cascade (YomiToku + manga-ocr + torch) OOM
    # the whole container — measured to need far more than a 512MB instance
    # provides. Digital PDFs (PyMuPDF text extraction, no ML models) are
    # measurably fine on 512MB and are unaffected either way — see
    # ingest_service.check_low_memory_support. Set true for a Render
    # 512MB deployment; leave false for local dev / a larger instance.
    low_memory_mode: bool = Field(default=False, validation_alias="LOW_MEMORY_MODE")

    app_env: str = "development"
    cors_origins: str = "http://localhost:5173"
    max_upload_mb: int = 25
    upload_dir: Path = BACKEND_DIR / "data" / "uploads"
    output_dir: Path = BACKEND_DIR / "data" / "output"
    temp_dir: Path = BACKEND_DIR / "data" / "tmp"
    cache_dir: Path = BACKEND_DIR / "data" / "cache"
    log_level: str = "INFO"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def groq_configured(self) -> bool:
        return bool(self.groq_api_key)

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def cloud_provider(self) -> str:
        """The cloud provider to actually use: the configured `llm_provider`
        preference if it has credentials, else whichever of groq/gemini does
        (so a half-configured .env degrades gracefully instead of raising).
        """
        preferred = self.llm_provider.lower()
        if preferred == "gemini" and self.gemini_configured:
            return "gemini"
        if preferred == "groq" and self.groq_configured:
            return "groq"
        if self.groq_configured:
            return "groq"
        if self.gemini_configured:
            return "gemini"
        return preferred

    @property
    def cloud_configured(self) -> bool:
        return self.groq_configured or self.gemini_configured

    @property
    def database_configured(self) -> bool:
        return bool(self.database_url)

    @property
    def redis_configured(self) -> bool:
        return bool(self.redis_url)

    @property
    def slack_configured(self) -> bool:
        return bool(self.slack_webhook_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
