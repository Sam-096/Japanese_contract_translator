"""Post-request glibc heap trim.

What this actually does: CPython's allocator frees objects back to its own
internal arenas, not straight back to the OS — after a request that
allocates a large short-lived buffer (an uploaded file read into memory, a
rasterized page, a rendered PDF), that memory can sit in glibc's heap,
inflating the process's resident set size (RSS) even though nothing is
using it anymore. `malloc_trim(0)` asks glibc to release those unused
arenas back to the OS, which the RSS the Render OOM killer looks at.

What this does NOT do: reduce PEAK memory during a request. If loading a
model or processing a page needs more RAM than the container has *at that
moment*, trimming afterward doesn't help — the OOM kill already happened.
This is worthwhile hygiene between requests, not a fix for a workload that
doesn't fit the container to begin with.

Linux-only (glibc). No-ops safely everywhere else (this dev machine is
Windows; Render's containers are Linux) — never let a missing libc break
the app.
"""
from __future__ import annotations

import ctypes
import logging
import sys

logger = logging.getLogger("app.memory")

_libc = None
_attempted = False


def _get_libc():
    global _libc, _attempted
    if _attempted:
        return _libc
    _attempted = True
    if sys.platform.startswith("linux"):
        try:
            _libc = ctypes.CDLL("libc.so.6")
        except OSError:
            logger.warning("libc.so.6 not loadable — malloc_trim disabled", exc_info=True)
    return _libc


def trim() -> None:
    libc = _get_libc()
    if libc is None:
        return
    try:
        libc.malloc_trim(0)
    except Exception:
        logger.warning("malloc_trim call failed", exc_info=True)


class MemoryTrimMiddleware:
    """Raw ASGI middleware (not BaseHTTPMiddleware, which buffers/wraps the
    response and can misbehave with the streaming file-export responses
    routes_export.py returns) — trims the glibc heap once the response has
    fully finished sending, on both the success and exception paths.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send)
        finally:
            trim()
