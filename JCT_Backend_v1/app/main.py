from __future__ import annotations

import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import routes_export, routes_jobs, routes_preview, routes_upload
from app.core import notifications
from app.core.config import get_settings
from app.core.error_catalog import present
from app.core.exceptions import AppError
from app.core.logging import configure_logging
from app.core.memory import MemoryTrimMiddleware

configure_logging()
settings = get_settings()
logger = logging.getLogger("app.main")

app = FastAPI(title="Japanese Document Translation Platform", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# See core/memory.py: trims glibc's heap back to the OS after every request
# (Linux-only, no-ops elsewhere). Real hygiene for RSS creep between
# requests; NOT a fix for a single request needing more peak memory than
# the container has (that OOM already happened by the time this would run).
app.add_middleware(MemoryTrimMiddleware)


# Same user-safe/developer-telemetry split as job_service.set_error — these
# two handlers cover AppErrors/crashes raised synchronously in a route
# (before a background job even exists), e.g. upload validation failures.
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    presentation = present(exc.code)
    logger.warning("AppError [%s]: %s", exc.code, exc.message)
    if presentation.alert_slack:
        notifications.send_slack_alert(
            severity=presentation.severity,
            title=f"{presentation.title} ({exc.code})",
            detail=exc.message,
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "ok": False,
            "data": None,
            "error": {
                "code": exc.code,
                "message": presentation.message,
                "severity": presentation.severity,
                "details": {},
            },
        },
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    tb = traceback.format_exc()[-1500:]
    notifications.send_slack_alert(
        severity="critical",
        title="Unhandled exception (INTERNAL_ERROR)",
        detail=f"{type(exc).__name__}: {exc}\n```{tb}```",
    )
    return JSONResponse(
        status_code=500,
        content={
            "ok": False,
            "data": None,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred. Please try again shortly.",
                "severity": "critical",
                "details": {},
            },
        },
    )


app.include_router(routes_upload.router, tags=["upload"])
app.include_router(routes_jobs.router, tags=["jobs"])
app.include_router(routes_preview.router, tags=["preview"])
app.include_router(routes_export.router, tags=["export"])


@app.get("/health")
async def health():
    return {"ok": True, "data": {"status": "up"}, "error": None}
