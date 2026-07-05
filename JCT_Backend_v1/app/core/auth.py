"""Bearer-token guard for the Render<->HF hybrid deployment.

An HF Space's URL is public and guessable (it's derived from the account +
Space name). Without this, anyone who finds it could hit the OCR-heavy
/upload endpoint directly — real compute cost, no way to attribute it. When
EXT_CLNT_KEY is configured, every request to the HF side except /health must
carry `Authorization: Bearer <EXT_CLNT_KEY>`; Render's proxy calls
(core/proxy.py) send this automatically. Unset EXT_CLNT_KEY = no
enforcement, so a standalone deployment not part of a pair is unaffected.

Only enforced when `deployment_name == "hf"` — Render is the public front
door the browser/frontend hits directly with no bearer token at all (it has
no way to know this shared secret, and shouldn't need to), so it must never
be gated by this itself. Caught live: an early version of this middleware
enforced on both sides equally and broke Render's own /upload for the
actual frontend the moment EXT_CLNT_KEY was set on both.
"""
from __future__ import annotations

from fastapi.responses import JSONResponse

from app.core.config import get_settings

_EXEMPT_PATHS = {"/health"}


class ClientAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        settings = get_settings()
        if (
            not settings.ext_clnt_key
            or settings.deployment_name != "hf"
            or scope["path"] in _EXEMPT_PATHS
        ):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization", b"").decode("latin-1")
        if auth != f"Bearer {settings.ext_clnt_key}":
            response = JSONResponse(
                status_code=401,
                content={
                    "ok": False,
                    "data": None,
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Missing or invalid credentials.",
                        "severity": "error",
                        "details": {},
                    },
                },
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
