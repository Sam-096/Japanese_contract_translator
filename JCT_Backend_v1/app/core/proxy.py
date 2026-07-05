"""HTTP proxy helpers for the Render<->HF hybrid deployment.

Render forwards scanned-PDF/image uploads to the HF Space (which has the
RAM for YomiToku/manga-ocr/torch — see LOW_MEMORY_MODE) instead of
rejecting them, and proxies the original-file-preview endpoint back through
HF when Render doesn't have those bytes locally. Everything else — job
status, translation JSON, PDF/XLSX export — needs no proxy logic at all:
both deployments share the same Postgres DB, and export rendering
(render_service.py) only ever reads the translated Document JSON already
sitting in that DB, never the original file — confirmed by grep before
building this (see JCT_Backend_v1 commit history / conversation notes).
"""
from __future__ import annotations

from fastapi.responses import Response

from app.core.config import get_settings
from app.core.exceptions import HFProxyError


def _hf_headers() -> dict[str, str]:
    settings = get_settings()
    return {"Authorization": f"Bearer {settings.ext_clnt_key}"} if settings.ext_clnt_key else {}


async def forward_upload_to_hf(filename: str, content: bytes) -> dict:
    """POST the raw upload to HF's own /upload endpoint and hand back its
    response verbatim — HF's route creates the actual document/job records
    (in the DB both deployments share) and processes it with its own OCR
    stack. Render never creates a local record for a document it hands off
    this way.
    """
    import httpx

    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{settings.hf_space_url.rstrip('/')}/upload",
                files={"file": (filename, content)},
                headers=_hf_headers(),
            )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        raise HFProxyError(
            f"HF proxy upload failed ({exc.response.status_code}): {exc.response.text}"
        ) from exc
    except httpx.HTTPError as exc:
        raise HFProxyError(f"HF proxy upload failed: {exc}") from exc


async def proxy_get(path: str) -> Response:
    """Forward a GET to the paired HF Space and relay its response bytes
    and content-type back unchanged. Used for the original-file preview
    endpoint when Render's own copy of the document isn't local — see
    routes_preview.py.
    """
    import httpx

    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{settings.hf_space_url.rstrip('/')}{path}", headers=_hf_headers()
            )
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HFProxyError(
            f"HF proxy GET {path} failed ({exc.response.status_code}): {exc.response.text}"
        ) from exc
    except httpx.HTTPError as exc:
        raise HFProxyError(f"HF proxy GET {path} failed: {exc}") from exc

    media_type = resp.headers.get("content-type", "application/octet-stream")
    return Response(content=resp.content, media_type=media_type)
