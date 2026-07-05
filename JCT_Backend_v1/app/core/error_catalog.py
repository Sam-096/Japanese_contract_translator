"""Maps each AppError `code` (see core/exceptions.py) to what the USER sees
vs. what gets Slack-alerted to developers — the "never expose internal
technical debt to the user, never hide it from the developer" split.

`present(code)` never fails to return something: an unrecognized code (a new
exception class added without a catalog entry, or a raw code string typo)
falls back to `_DEFAULT` rather than leaking whatever the raw exception
message says.

`alert_slack=False` entries are user-input problems (bad file, missing
document) — normal usage, not something a developer needs paging for.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorPresentation:
    severity: str  # "warning" | "error" | "critical"
    title: str
    message: str
    alert_slack: bool


_SERVICE_INTERRUPTED = ErrorPresentation(
    severity="critical",
    title="Translation Service Interrupted",
    message="Our translation service is temporarily unavailable. The team has been notified — please try again shortly.",
    alert_slack=True,
)

_CATALOG: dict[str, ErrorPresentation] = {
    "UPLOAD_TOO_LARGE": ErrorPresentation(
        "error", "File Too Large", "This file is too large to upload.", False
    ),
    "UNSUPPORTED_FILE_TYPE": ErrorPresentation(
        "error", "Unsupported File",
        "This file type isn't supported. Try a PDF, PNG, JPG, or TIFF.", False,
    ),
    "PDF_PASSWORD_PROTECTED": ErrorPresentation(
        "error", "Cannot Read Document",
        "This file appears to be encrypted or password-protected. Please remove protection and try again.", False,
    ),
    "CORRUPT_FILE": ErrorPresentation(
        "error", "Cannot Read Document",
        "This file couldn't be read — it may be corrupt. Please try re-saving it as a standard PDF or image.", False,
    ),
    "OCR_FAILED": ErrorPresentation(
        "error", "Processing Interrupted",
        "This document is exceptionally dense or complex and some pages couldn't be fully processed. "
        "Please verify the file contains clear, legible text.", True,
    ),
    "SCANNED_DOCUMENT_UNSUPPORTED": ErrorPresentation(
        "error", "Scanned Documents Not Supported",
        "This document appears to be a scanned image rather than a text-based PDF. "
        "Scanned-document translation isn't available on this deployment right now — "
        "please upload a digital PDF with a selectable text layer.",
        False,  # expected, by-design behavior on this tier — not a bug to page anyone for
    ),
    "TRANSLATION_TIMEOUT": ErrorPresentation(
        "error", "Processing Interrupted",
        "This document is exceptionally dense or complex, and processing took too long. "
        "Please try again or use a smaller file.", True,
    ),
    "TRANSLATION_UNAVAILABLE": _SERVICE_INTERRUPTED,
    "PROVIDER_CAPACITY": _SERVICE_INTERRUPTED,
    "GROQ_RATE_LIMITED": _SERVICE_INTERRUPTED,
    "GEMINI_RATE_LIMITED": _SERVICE_INTERRUPTED,
    "EXPORT_FAILED": ErrorPresentation(
        "error", "Export Failed", "We couldn't generate your download. Please try again.", True
    ),
    "JOB_NOT_FOUND": ErrorPresentation(
        "error", "Job Not Found", "We couldn't find this translation job. It may have expired.", False
    ),
    "DOCUMENT_NOT_FOUND": ErrorPresentation(
        "error", "Document Not Found", "We couldn't find this document. It may have expired.", False
    ),
    "HF_PROXY_FAILED": ErrorPresentation(
        "critical", "Processing Interrupted",
        "This document requires additional processing that's temporarily unavailable. "
        "The team has been notified — please try again shortly.",
        True,  # the Render<->HF pairing itself is broken — always worth paging for
    ),
    "UNAUTHORIZED": ErrorPresentation(
        "error", "Unauthorized", "Missing or invalid credentials.", False
    ),
    "INTERNAL_ERROR": _SERVICE_INTERRUPTED,
}

_DEFAULT = _SERVICE_INTERRUPTED


def present(code: str) -> ErrorPresentation:
    return _CATALOG.get(code, _DEFAULT)
