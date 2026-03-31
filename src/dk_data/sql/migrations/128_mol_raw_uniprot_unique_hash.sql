-- Migration 128: Add UNIQUE(response_body_hash) to mol_raw.uniprot
-- Feature: 021-post-deploy-fixes
--
-- Context: mol_raw.uniprot was created in migration 020 without a UNIQUE
-- constraint on response_body_hash. The uniprot source is a static query
-- (reviewed human kinase proteins) that returns the same ~500 records on
-- every weekly run. Without a unique constraint:
--   - ON CONFLICT DO NOTHING in sources/uniprot.py had no effect (only
--     the UUID PK was checked, which is always a new value)
--   - 500 duplicate rows accumulated each weekly run
--
-- Fix: Add UNIQUE(response_body_hash). The loader was simultaneously updated
-- to use ON CONFLICT (response_body_hash) DO NOTHING, preventing duplicates.
-- Any existing duplicates are handled by first removing them before adding
-- the constraint.

BEGIN;

-- Remove duplicate rows (keep the oldest ingested copy of each hash)
DELETE FROM mol_raw.uniprot
WHERE id NOT IN (
    SELECT DISTINCT ON (response_body_hash) id
    FROM mol_raw.uniprot
    ORDER BY response_body_hash, ingested_at ASC
)
AND response_body_hash IS NOT NULL;

-- Add UNIQUE constraint
ALTER TABLE mol_raw.uniprot
    ADD CONSTRAINT uq_mol_raw_uniprot_body_hash
    UNIQUE (response_body_hash);

COMMIT;
