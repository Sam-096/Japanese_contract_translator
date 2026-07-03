"""Postgres connection pool (psycopg3, sync — matches the existing
ThreadPoolExecutor background-job model in job_service.py, not asyncio).

document_store.py and job_service.py both check `settings.database_configured`
before touching this module, so importing psycopg only happens when a
DATABASE_URL is actually set.

`prepare_threshold=None` disables psycopg3's automatic server-side prepared
statements. DATABASE_URL points at Supabase's *transaction-mode* pooler
(see .env.example) — in transaction mode, PgBouncer can route two queries
from the same logical connection to two different backend Postgres
connections. A prepared statement created on backend A doesn't exist on
backend B, so psycopg's default auto-prepare-after-5-executions intermittently
raises `DuplicatePreparedStatement`/`prepared statement does not exist`
under load (reproduced live: a `GET /jobs/{id}` poll crashed with exactly
this during a long-running translation with many status polls).
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from psycopg import Connection
from psycopg_pool import ConnectionPool

from app.core.config import get_settings

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = ConnectionPool(
            settings.database_url,
            # Capped at 3 (was 5): the only concurrent DB users are
            # job_service's 2-worker ThreadPoolExecutor plus request-handling
            # coroutines, which on a single-uvicorn-worker 512MB instance
            # rarely need more than a couple at once. Each idle pooled
            # connection costs real (if modest) resident memory, so this
            # isn't padded beyond what's actually used.
            min_size=1,
            max_size=3,
            open=True,
            kwargs={"prepare_threshold": None},
        )
    return _pool


@contextmanager
def get_conn() -> Iterator[Connection]:
    with get_pool().connection() as conn:
        yield conn
