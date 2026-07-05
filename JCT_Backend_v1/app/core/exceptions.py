"""Structured application errors -> consistent {"ok": false, "error": {...}} envelopes."""
from __future__ import annotations


class AppError(Exception):
    code = "INTERNAL_ERROR"
    status_code = 500

    def __init__(self, message: str, details: dict | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)


class UploadTooLargeError(AppError):
    code = "UPLOAD_TOO_LARGE"
    status_code = 413


class UnsupportedFileTypeError(AppError):
    code = "UNSUPPORTED_FILE_TYPE"
    status_code = 415


class PasswordProtectedPdfError(AppError):
    code = "PDF_PASSWORD_PROTECTED"
    status_code = 422


class CorruptFileError(AppError):
    code = "CORRUPT_FILE"
    status_code = 422


class OcrFailedError(AppError):
    code = "OCR_FAILED"
    status_code = 422


class ScannedDocumentUnsupportedError(AppError):
    """Raised by ingest_service._check_low_memory_support, early inside
    run_ingest — same pattern as PasswordProtectedPdfError: the job is
    already created (POST /upload returns 200 with a job_id as usual), and
    this fails the job cleanly via job_service.submit's exception handler
    before pipeline.process() would reach the OCR cascade (YomiToku +
    manga-ocr + torch) for a scanned PDF/image. That cascade needs far more
    RAM than a 512MB instance has; letting it start would OOM-crash the
    whole container instead of just failing this one job.

    Only reached when LOW_MEMORY_MODE is true AND no HF_SPACE_URL is
    configured (a standalone memory-constrained deployment with no proxy
    partner) — when HF_SPACE_URL IS set, routes_upload.py forwards the
    upload to it instead of raising this (see core/proxy.py).
    """
    code = "SCANNED_DOCUMENT_UNSUPPORTED"
    status_code = 422


class HFProxyError(AppError):
    """The Render->HF proxy call itself failed (network error, HF Space
    asleep/cold-starting, non-2xx response) — see core/proxy.py. Distinct
    from a translation-quality failure: this means the request never even
    reached HF's actual processing.
    """
    code = "HF_PROXY_FAILED"
    status_code = 502


class UnauthorizedError(AppError):
    """Raised by core/auth.ClientAuthMiddleware when EXT_CLNT_KEY is
    configured and the request's Authorization header doesn't match — e.g.
    someone hitting the HF Space's public URL directly without the shared
    secret Render sends.
    """
    code = "UNAUTHORIZED"
    status_code = 401


class TranslationTimeoutError(AppError):
    code = "TRANSLATION_TIMEOUT"
    status_code = 504


class TranslationUnavailableError(AppError):
    code = "TRANSLATION_UNAVAILABLE"
    status_code = 503


class ProviderCapacityError(AppError):
    """Base for a cloud translation provider being temporarily unable to
    serve a request (429 rate limit, 503 unavailable, connection failure).
    translate_service.py catches this specifically to trigger an automatic
    retry with the other configured provider (see _translate_with_fallback).
    """
    code = "PROVIDER_CAPACITY"
    status_code = 503


class GroqRateLimitedError(ProviderCapacityError):
    code = "GROQ_RATE_LIMITED"
    status_code = 429


class GeminiRateLimitedError(ProviderCapacityError):
    code = "GEMINI_RATE_LIMITED"
    status_code = 429


class ExportFailedError(AppError):
    code = "EXPORT_FAILED"
    status_code = 500


class JobNotFoundError(AppError):
    code = "JOB_NOT_FOUND"
    status_code = 404


class DocumentNotFoundError(AppError):
    code = "DOCUMENT_NOT_FOUND"
    status_code = 404
