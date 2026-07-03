"""Slack alerting — the developer-facing half of the error-notification
split (see error_catalog.py for the user-facing half). The client only ever
sees a friendly `error_catalog.ErrorPresentation.message`; the raw exception
text, error code, and (for crashes) traceback go here instead.

Never raises: an alert failing to send must never break the request/job it's
reporting on. Degrades to a log line if SLACK_WEBHOOK_URL is unset or the
POST fails for any reason (network, bad webhook, Slack outage).
"""
from __future__ import annotations

import logging

from app.core.config import get_settings

logger = logging.getLogger("app.notifications")

_SEVERITY_EMOJI = {
    "warning": ":warning:",
    "error": ":x:",
    "critical": ":rotating_light:",
}


def send_slack_alert(*, severity: str, title: str, detail: str, job_id: str | None = None) -> None:
    settings = get_settings()
    if not settings.slack_configured:
        logger.info("Slack alert skipped (not configured): [%s] %s — %s", severity, title, detail)
        return

    emoji = _SEVERITY_EMOJI.get(severity, ":information_source:")
    lines = [f"{emoji} *{title}*", detail]
    if job_id:
        lines.append(f"job_id: `{job_id}`")
    text = "\n".join(lines)[:3800]  # stay well under Slack's per-message limit

    try:
        import httpx

        resp = httpx.post(settings.slack_webhook_url, json={"text": text}, timeout=5)
        resp.raise_for_status()
    except Exception:
        logger.warning("Slack alert failed to send: [%s] %s", severity, title, exc_info=True)
