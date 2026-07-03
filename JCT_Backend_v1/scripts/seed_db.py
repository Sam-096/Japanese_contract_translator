"""Seed glossary_terms from the live src/jpdoc/glossary.py LEGAL_TERMS dict —
that Python dict stays the single source of truth (it's what the translation
pipeline actually reads on every call); this script just mirrors it into the DB
for visibility/audit/future admin-UI editing. Safe to re-run (upserts by jp_term).

Usage:
    cd JCT_Backend_v1 && ../.venv/Scripts/python.exe scripts/seed_db.py
Requires DATABASE_URL in JCT_Backend_v1/.env (see JCT_Backend_v1/db/schema.sql for the schema —
run that first, in the Supabase SQL editor or via psql).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # JCT_Backend_v1/ for `app`
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))  # src/ for `jpdoc`

from app.core.config import get_settings  # noqa: E402
from jpdoc.glossary import LEGAL_TERMS  # noqa: E402


def main() -> None:
    settings = get_settings()
    if not settings.database_url:
        print("DATABASE_URL is not set in JCT_Backend_v1/.env — nothing to do.")
        return

    import psycopg

    with psycopg.connect(settings.database_url) as conn, conn.cursor() as cur:
        for jp_term, en_term in LEGAL_TERMS.items():
            cur.execute(
                """
                INSERT INTO glossary_terms (jp_term, en_term)
                VALUES (%s, %s)
                ON CONFLICT (jp_term) DO UPDATE SET en_term = EXCLUDED.en_term
                """,
                (jp_term, en_term),
            )
        conn.commit()

    print(f"Seeded {len(LEGAL_TERMS)} glossary terms.")


if __name__ == "__main__":
    main()
