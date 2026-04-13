-- Migration: 220_align_source_naming
-- Feature: 002-external-integration-foundation (US-20, T131)
-- GitHub issue: data-kinetic/dk-data-FE#277
--
-- Purpose: Align `meta.backfill_state.source_name` to match the canonical
-- raw table name for six sources whose backfill_state entries drifted
-- away from their raw table names over time. This is a pure metadata
-- update — no raw tables are renamed, no data is moved.
--
-- Sources aligned (6 total):
--
--   old backfill_state    new backfill_state       raw table
--   ─────────────────     ────────────────────     ─────────────────
--   epo_ops               epo_patents              ip_raw.epo_patents
--   cochrane              cochrane_reviews         mol_raw.cochrane_reviews
--   ema_mol               ema                      mol_raw.ema
--   hta_bodies            hta_decisions            mol_raw.hta_decisions
--   hrsa                  hrsa_shortage_areas      hcs_raw.hrsa_shortage_areas
--
-- NOT aligned (deferred):
--   chembl_molecules stays as-is in backfill_state. Renaming it would
--   require also renaming mol_raw.chembl → mol_raw.chembl_molecules,
--   which would break every downstream SQLMesh model that references
--   mol_raw.chembl. That's out of scope for this initiative (see spec
--   Non-Goals section for the explicit deferral).
--
-- Idempotent: UPDATE WHERE source_name = 'old' is safe to re-run. If
-- the alignment has already happened, the UPDATE affects zero rows.
--
-- Run: psql -h localhost -p 5433 -U postgres -d dk_data -f migrations/220_align_source_naming.sql

BEGIN;

SET LOCAL statement_timeout = '30s';
SET LOCAL lock_timeout = '10s';

-- -----------------------------------------------------------------------------
-- Pre-check: meta.backfill_state must exist.
-- -----------------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'meta' AND table_name = 'backfill_state'
    ) THEN
        RAISE EXCEPTION 'meta.backfill_state does not exist — run migration 165_meta_backfill_state.sql first';
    END IF;
END $$;

-- -----------------------------------------------------------------------------
-- 1. Apply the 5 renames. Each UPDATE is idempotent.
--
-- Using `WHERE NOT EXISTS (SELECT ... WHERE source_name = 'new')` guards
-- against a collision if both the old and new rows somehow coexist
-- (shouldn't happen, but be defensive).
-- -----------------------------------------------------------------------------

DO $$
DECLARE
    rename_map TEXT[][] := ARRAY[
        ['epo_ops',      'epo_patents'],
        ['cochrane',     'cochrane_reviews'],
        ['ema_mol',      'ema'],
        ['hta_bodies',   'hta_decisions'],
        ['hrsa',         'hrsa_shortage_areas']
    ];
    old_name TEXT;
    new_name TEXT;
    updated_rows INT;
    i INT;
BEGIN
    FOR i IN 1 .. array_length(rename_map, 1) LOOP
        old_name := rename_map[i][1];
        new_name := rename_map[i][2];

        -- Guard against collision: skip if target already exists.
        IF EXISTS (
            SELECT 1 FROM meta.backfill_state WHERE source_name = new_name
        ) THEN
            -- Target already exists. If the source also exists, that's
            -- a dup — leave it for operator cleanup.
            IF EXISTS (
                SELECT 1 FROM meta.backfill_state WHERE source_name = old_name
            ) THEN
                RAISE WARNING
                    'source_name collision: both % and % exist in meta.backfill_state — manual cleanup required',
                    old_name, new_name;
            ELSE
                RAISE NOTICE 'rename % → % already applied (new name present, old name absent)',
                    old_name, new_name;
            END IF;
            CONTINUE;
        END IF;

        UPDATE meta.backfill_state
        SET source_name = new_name
        WHERE source_name = old_name;

        GET DIAGNOSTICS updated_rows = ROW_COUNT;

        IF updated_rows > 0 THEN
            RAISE NOTICE 'renamed % → % (% row(s))', old_name, new_name, updated_rows;
        ELSE
            RAISE NOTICE 'source_name = % not found in meta.backfill_state — skipping',
                old_name;
        END IF;
    END LOOP;
END $$;

-- -----------------------------------------------------------------------------
-- 2. ANALYZE so the query planner picks up the updated source_name values
--    (backfill_state has a PRIMARY KEY on source_name so this isn't strictly
--    necessary for correctness, but it's cheap and good hygiene after DML).
-- -----------------------------------------------------------------------------

ANALYZE meta.backfill_state;

-- -----------------------------------------------------------------------------
-- COMPLETION
-- -----------------------------------------------------------------------------

DO $$
BEGIN
    RAISE NOTICE '220_align_source_naming complete: 5 source names aligned to canonical raw table names';
    RAISE NOTICE 'NEXT STEPS (separate PRs):';
    RAISE NOTICE '  1. Update ingestion module references: src/dk_data/ingestion/sources/*.py';
    RAISE NOTICE '  2. Update cronjob YAML references: k8s/apps/cronjobs/base/';
    RAISE NOTICE '  3. Update metering proxy consumers.yaml allowlists if any referenced the old names';
    RAISE NOTICE '  4. Add CI check enforcing naming consistency (T135)';
END $$;

COMMIT;
