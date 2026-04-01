-- Migration 138: Schema integrity fixes
-- Issues: #191, #189, #188, #187
-- Branch: 025-schema-integrity-stability
--
-- Fixes:
--   (a) Rename meta.refresh_log columns to match application code
--   (b) Add UNIQUE expression indexes for ON CONFLICT upserts
--   (c) Ensure mol_raw.cdc_vaccines table exists
--   (d) Ensure meta.data_sources entry for cdc_vaccines exists
--   (e) Column name drift: ingested_at → _loaded_at / fetched_at (idempotent)
--   (f) Type drift fixes from migration 137
--   (g) Add mol_raw.cochrane_reviews.pmid column (idempotent)
--   (h) Fix mol_raw.cochrane_reviews.interventions/conditions JSONB → TEXT[] (idempotent)
--   (i) Drop orphaned raw.cochrane_reviews table

-- ============================================================================
-- (a) meta.refresh_log — rename started_at → refresh_started_at,
--     completed_at → refresh_completed_at (idempotent)
-- ============================================================================

DO $migrate$
BEGIN
    -- Only rename if the old column names still exist
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'meta'
          AND table_name   = 'refresh_log'
          AND column_name  = 'started_at'
    ) THEN
        ALTER TABLE meta.refresh_log RENAME COLUMN started_at TO refresh_started_at;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'meta'
          AND table_name   = 'refresh_log'
          AND column_name  = 'completed_at'
    ) THEN
        ALTER TABLE meta.refresh_log RENAME COLUMN completed_at TO refresh_completed_at;
    END IF;
END
$migrate$;

-- Recreate indexes to use new column names (idempotent)
DROP INDEX IF EXISTS meta.idx_refresh_log_source_status;
CREATE INDEX IF NOT EXISTS idx_refresh_log_source_status
    ON meta.refresh_log (source_id, status, refresh_started_at DESC);

-- Note: meta.refresh_log has source_id (FK), not source_name.
-- Drop the old mis-named index if it existed; no replacement needed since
-- idx_refresh_log_source_status already covers (source_id, status, started_at).
DROP INDEX IF EXISTS meta.idx_refresh_log_source_name;

-- ============================================================================
-- (b) UNIQUE expression indexes for ON CONFLICT upserts
-- ============================================================================

-- pubchem: loader uses ON CONFLICT ((response_body->>'cid')) WHERE (response_body->>'cid') IS NOT NULL
-- Partial index required — PostgreSQL ON CONFLICT must match index predicate exactly.
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_pubchem_cid
    ON mol_raw.pubchem ((response_body->>'cid'))
    WHERE (response_body->>'cid') IS NOT NULL;

-- chembl: loader uses ON CONFLICT ((response_body->>'molecule_chembl_id')) WHERE ... IS NOT NULL
-- Note: table is mol_raw.chembl (not chembl_molecules); loader file is chembl_molecules.py
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_chembl_chembl_id
    ON mol_raw.chembl ((response_body->>'molecule_chembl_id'))
    WHERE (response_body->>'molecule_chembl_id') IS NOT NULL;

-- who_gho: loader uses ON CONFLICT ((response_body->>'IndicatorCode')) WHERE ... IS NOT NULL
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_who_gho_indicator_code
    ON mol_raw.who_gho ((response_body->>'IndicatorCode'))
    WHERE (response_body->>'IndicatorCode') IS NOT NULL;

-- ============================================================================
-- (c) mol_raw.cdc_vaccines — safety net if migration 121 was not applied
-- ============================================================================

CREATE TABLE IF NOT EXISTS mol_raw.cdc_vaccines (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint        TEXT,
    api_version         TEXT,
    request_params      JSONB,
    request_headers     JSONB,
    response_status     INTEGER,
    response_headers    JSONB,
    response_body       JSONB NOT NULL,
    response_body_hash  TEXT,
    response_size_bytes INTEGER,
    response_time_ms    INTEGER,
    processed_to_bronze BOOLEAN NOT NULL DEFAULT FALSE,
    processed_at        TIMESTAMPTZ,
    processing_error    TEXT,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id           TEXT,
    CONSTRAINT uidx_mol_raw_cdc_vaccines_request_id UNIQUE (request_id)
);

CREATE INDEX IF NOT EXISTS idx_mol_raw_cdc_vaccines_ts
    ON mol_raw.cdc_vaccines (ingested_at);
CREATE INDEX IF NOT EXISTS idx_mol_raw_cdc_vaccines_bronze
    ON mol_raw.cdc_vaccines (processed_to_bronze) WHERE NOT processed_to_bronze;

-- ============================================================================
-- (d) meta.data_sources entry for cdc_vaccines
-- ============================================================================

INSERT INTO meta.data_sources (source_name, source_type, source_url, description, is_active)
VALUES (
    'cdc_vaccines',
    'api',
    'https://data.cdc.gov/resource/b7pe-5nws.json',
    'CDC vaccine adverse event data',
    true
)
ON CONFLICT (source_name) DO NOTHING;

-- ============================================================================
-- (e) Column name drift: migration 137 originally used "ingested_at" in
--     domain mol_raw tables but loaders & bronze models expect "_loaded_at"
--     (or "fetched_at" for orcid). Migration 137 has since been corrected to
--     use the right names directly, but this block runs idempotently for any
--     environment that already applied the original migration 137.
-- ============================================================================

DO $col_rename$
DECLARE
    _tbl TEXT;
BEGIN
    -- Tables that need ingested_at → _loaded_at
    FOR _tbl IN
        SELECT unnest(ARRAY[
            'cochrane_reviews', 'ema_regulatory', 'epo_patents',
            'euipo_designs', 'euipo_trademarks', 'hta_decisions',
            'journal_rss', 'medical_news', 'openalex_ci', 'pubmed',
            'sec_edgar', 'uspto_ci', 'uspto_patents', 'uspto_trademarks'
        ])
    LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'mol_raw'
              AND table_name   = _tbl
              AND column_name  = 'ingested_at'
        ) AND NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'mol_raw'
              AND table_name   = _tbl
              AND column_name  = '_loaded_at'
        ) THEN
            EXECUTE format(
                'ALTER TABLE mol_raw.%I RENAME COLUMN ingested_at TO _loaded_at', _tbl
            );
        END IF;
    END LOOP;

    -- orcid: ingested_at → fetched_at
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'mol_raw'
          AND table_name   = 'orcid'
          AND column_name  = 'ingested_at'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'mol_raw'
          AND table_name   = 'orcid'
          AND column_name  = 'fetched_at'
    ) THEN
        ALTER TABLE mol_raw.orcid RENAME COLUMN ingested_at TO fetched_at;
    END IF;
END
$col_rename$;

-- ============================================================================
-- (f) Type drift fixes from migration 137 (idempotent)
-- ============================================================================

-- openalex_ci.cited_by_percentile: JSONB → NUMERIC (matches migration 136 ALTER)
DO $type_fix$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'mol_raw'
          AND table_name   = 'openalex_ci'
          AND column_name  = 'cited_by_percentile'
          AND data_type    = 'jsonb'
    ) THEN
        ALTER TABLE mol_raw.openalex_ci
            ALTER COLUMN cited_by_percentile TYPE NUMERIC USING NULL;
    END IF;

    -- epo_patents.ipc_codes: JSONB → TEXT[] (matches migration 108 ALTER)
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'mol_raw'
          AND table_name   = 'epo_patents'
          AND column_name  = 'ipc_codes'
          AND data_type    = 'jsonb'
    ) THEN
        ALTER TABLE mol_raw.epo_patents
            ALTER COLUMN ipc_codes TYPE TEXT[] USING NULL;
    END IF;
END
$type_fix$;

-- ============================================================================
-- (g) mol_raw.cochrane_reviews — add pmid column (idempotent)
--     Migration 137 has been corrected to include pmid, but existing clusters
--     need the column added.
-- ============================================================================

ALTER TABLE mol_raw.cochrane_reviews
    ADD COLUMN IF NOT EXISTS pmid TEXT;

CREATE INDEX IF NOT EXISTS idx_mol_raw_cochrane_pmid ON mol_raw.cochrane_reviews (pmid);

-- ============================================================================
-- (h) mol_raw.cochrane_reviews — fix interventions/conditions JSONB → TEXT[]
--     Validator declares Optional[list[str]] which maps to TEXT[].
--     The JSONB type was a mistake in the original migration 137 DDL.
-- ============================================================================

DO $cochrane_type_fix$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'mol_raw'
          AND table_name   = 'cochrane_reviews'
          AND column_name  = 'interventions'
          AND data_type    = 'jsonb'
    ) THEN
        ALTER TABLE mol_raw.cochrane_reviews
            ALTER COLUMN interventions TYPE TEXT[] USING NULL;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'mol_raw'
          AND table_name   = 'cochrane_reviews'
          AND column_name  = 'conditions'
          AND data_type    = 'jsonb'
    ) THEN
        ALTER TABLE mol_raw.cochrane_reviews
            ALTER COLUMN conditions TYPE TEXT[] USING NULL;
    END IF;
END
$cochrane_type_fix$;

-- ============================================================================
-- (i) Drop orphaned raw.cochrane_reviews (superseded by mol_raw.cochrane_reviews)
--     Created in migration 060; mol_raw version is canonical since the
--     codebase migrated from raw.* → mol_raw.*.
-- ============================================================================

DROP TABLE IF EXISTS raw.cochrane_reviews;
