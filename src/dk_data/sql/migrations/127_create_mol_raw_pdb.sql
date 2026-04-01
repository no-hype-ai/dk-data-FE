-- Migration 127: Create mol_raw.pdb (fix missed _safe_move_schema from 099)
-- Feature: 021-post-deploy-fixes
--
-- Context: Migration 099 ran _safe_move_schema('raw', 'pdb', 'mol_raw') but the
-- condition (raw.pdb EXISTS AND mol_raw.pdb NOT EXISTS) was not met at execution
-- time, so the rename was silently skipped. raw.pdb still exists with the old
-- typed schema (pdb_id, title, method, ...) while the current sources/pdb.py
-- loader targets mol_raw.pdb with the standard envelope schema.
--
-- Fix: Create mol_raw.pdb with the envelope schema (matching migration 028 pattern
-- used by all other mol_raw tables). Add UNIQUE(response_body_hash) to prevent
-- the weekly PDB fetch re-inserting the same 500 structures on every run.

BEGIN;

CREATE TABLE IF NOT EXISTS mol_raw.pdb (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL,
    api_version         VARCHAR(20),
    request_params      JSONB,
    request_headers     JSONB,
    response_status     INTEGER NOT NULL,
    response_headers    JSONB,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64) UNIQUE,
    response_size_bytes INTEGER,
    response_time_ms    INTEGER,
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    processed_at        TIMESTAMPTZ,
    processing_error    TEXT,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           VARCHAR(50) NOT NULL DEFAULT 'pdb'
);

CREATE INDEX IF NOT EXISTS idx_mol_raw_pdb_request_id  ON mol_raw.pdb(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_pdb_timestamp   ON mol_raw.pdb(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_mol_raw_pdb_processed   ON mol_raw.pdb(processed_to_bronze);
CREATE INDEX IF NOT EXISTS idx_mol_raw_pdb_ingested    ON mol_raw.pdb(ingested_at);

COMMIT;
