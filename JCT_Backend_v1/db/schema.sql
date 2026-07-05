-- Run this in the Supabase SQL editor (Project -> SQL Editor -> New query) once,
-- or via `psql "$DATABASE_URL" -f backend/db/schema.sql` for any Postgres target.
--
-- Design notes:
--   - `documents.document_json` stores the full nested Document (pages -> blocks ->
--     table cells, see src/jpdoc/schema.py) as JSONB rather than normalizing every
--     block/cell into its own table. The app always reads/writes this as one whole
--     object (never queries individual blocks via SQL), so normalizing would add
--     real complexity for no query benefit.
--   - `glossary_terms` mirrors src/jpdoc/glossary.py's LEGAL_TERMS dict, seeded by
--     backend/scripts/seed_db.py. The live translation pipeline still reads the
--     Python dict directly (glossary.preamble() runs on every translate call —
--     adding a live DB read to that hot path isn't worth it for a small,
--     rarely-changing glossary). This table is for visibility/audit/future
--     admin-UI editing, not a runtime dependency.
--   - `translation_cache` is the durable backing store for the Redis cache (Redis
--     is the hot path; this survives a Redis restart/eviction and gives an audit
--     trail). Keyed by sha256 of the source text so identical phrases — very
--     common in form labels and boilerplate clauses — are never re-translated.

CREATE EXTENSION IF NOT EXISTS pgcrypto; -- for gen_random_uuid()

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    original_filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    kind TEXT,
    document_json JSONB,
    translated BOOLEAN NOT NULL DEFAULT FALSE,
    translator_map JSONB NOT NULL DEFAULT '{}'::jsonb,
    export_paths JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Which physical deployment (settings.deployment_name — "render"/"hf")
    -- actually ingested this document and owns its local files. Lets a
    -- Render<->HF hybrid pair sharing this DB know whether a file-serving
    -- request (original-file preview) needs to be proxied to the other
    -- deployment. NULL for rows written before this column existed.
    processed_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS processed_by TEXT;

CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'queued',
    progress_message TEXT NOT NULL DEFAULT 'Queued',
    error JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_jobs_document_id ON jobs(document_id);

CREATE TABLE IF NOT EXISTS glossary_terms (
    id SERIAL PRIMARY KEY,
    jp_term TEXT NOT NULL UNIQUE,
    en_term TEXT NOT NULL,
    category TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS translation_cache (
    source_hash TEXT PRIMARY KEY,
    source_text TEXT NOT NULL,
    translated_text TEXT NOT NULL,
    translator TEXT NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Row Level Security: this backend connects via the direct Postgres connection
-- string (DATABASE_URL from Supabase's Project Settings -> Database), not through
-- Supabase's REST/PostgREST API, so RLS doesn't gate this server's own access.
-- It's enabled here anyway as defense-in-depth: if these tables are ever exposed
-- through Supabase's REST API to a browser using the anon/public key, no
-- policies means anon access is fully locked out by default rather than open.
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE glossary_terms ENABLE ROW LEVEL SECURITY;
ALTER TABLE translation_cache ENABLE ROW LEVEL SECURITY;
