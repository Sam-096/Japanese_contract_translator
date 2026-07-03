from __future__ import annotations

from typing import Any


def ok(data: Any) -> dict:
    return {"ok": True, "data": data, "error": None}
