"""Upload validation. Never trust the extension alone — sniff the file signature."""
from __future__ import annotations

from pathlib import PurePosixPath

from app.core.exceptions import UnsupportedFileTypeError, UploadTooLargeError

SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}

_SIGNATURES: list[tuple[bytes, str]] = [
    (b"%PDF-", "pdf"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"II*\x00", "tiff"),
    (b"MM\x00*", "tiff"),
]


def sniff_kind(header: bytes) -> str | None:
    for signature, kind in _SIGNATURES:
        if header.startswith(signature):
            return kind
    return None


def validate_upload(filename: str, content: bytes, max_mb: int) -> None:
    ext = PurePosixPath(filename.replace("\\", "/")).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileTypeError(
            f"Unsupported file type '{ext or '(none)'}'. Accepted: PDF, PNG, JPG, JPEG, TIFF."
        )
    if not content:
        raise UnsupportedFileTypeError("The uploaded file is empty.")
    if len(content) > max_mb * 1024 * 1024:
        raise UploadTooLargeError(f"File exceeds the {max_mb}MB upload limit.")
    if sniff_kind(content[:16]) is None:
        raise UnsupportedFileTypeError(
            "File content does not match a supported PDF/image signature."
        )
