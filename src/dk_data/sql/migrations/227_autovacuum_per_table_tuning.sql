-- Migration: 227_autovacuum_per_table_tuning
-- Feature: 002-external-integration-foundation (infra-freeze adaptation)
--
-- ## Problem
--
-- The CNPG cluster's global autovacuum defaults are too conservative
-- for dk-data's high-write tables. Ideal global values
-- (autovacuum_vacuum_scale_factor=0.05) require a CNPG cluster spec
-- change in the infra repo. Under the current infra freeze those
-- changes are pending (see docs/runbooks/postgres-tuning.md Group B).
--
-- ## Solution (this migration)
--
-- Per-table storage parameters set via `ALTER TABLE ... SET (...)`.
-- This is a DDL-only change — no data movement, no downtime,
-- no infra ticket needed. Settings take effect on the NEXT autovacuum
-- cycle after the migration runs.
--
-- ## Tables tuned and rationale
--
-- 1. mol_silver.publications  — ~15M rows, appended by every PubMed
--    bronze→silver run. Default scale_factor=0.2 means autovacuum only
--    kicks in after 3M dead tuples (20% × 15M). At our write rate,
--    that causes bloat to accumulate for days. Target: 2%.
--
-- 2. mol_raw.chembl_activities — ~50M rows after full backfill.
--    ON CONFLICT DO UPDATE generates dead tuples on every upsert.
--    Default scale_factor=0.2 → 10M dead tuples before vacuum.
--    Target: 2% with higher cost_limit to make vacuums faster.
--
-- 3. meta.transform_runs — append-only audit table, ~10k rows/day.
--    No dead tuples expected but analyze lag causes stale stats, which
--    leads to planner choosing full-scans on status-filtered queries.
--    Target: analyze_scale_factor=0.01 (1%) for fresh statistics.
--
-- 4. meta.api_audit_log — high-write append-only table. Same issue
--    as transform_runs: stale stats → bad query plans. Target: 1%.
--
-- 5. mol_silver.bioactivity — ~50M rows if the bioactivity backfill
--    runs. Guard with a conditional so this is a no-op if the table
--    doesn't exist yet. Target: 2%.
--
-- ## Safe / idempotent
--
-- `ALTER TABLE ... SET (...)` is idempotent. Re-running this migration
-- resets the values to the same target — no harm. It takes an
-- ACCESS SHARE lock (the weakest possible) for the parameter update.
-- pg_stat_user_tables shows the effect under `reltuples`/`n_dead_tup`.
--
-- ## Verification
--
-- After applying, confirm the settings took effect:
--
--   SELECT relname,
--          reloptions
--   FROM pg_class
--   WHERE relname IN (
--       'publications', 'chembl_activities', 'transform_runs',
--       'api_audit_log', 'bioactivity'
--   );
--
-- Expected: each row's reloptions array includes the values set below.

BEGIN;

SET LOCAL statement_timeout = '60s';
SET LOCAL lock_timeout = '10s';

-- 1. mol_silver.publications
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'mol_silver' AND table_name = 'publications'
    ) THEN
        EXECUTE $sql$
            ALTER TABLE mol_silver.publications SET (
                autovacuum_vacuum_scale_factor = 0.02,
                autovacuum_analyze_scale_factor = 0.01,
                autovacuum_vacuum_cost_limit = 1000
            )
        $sql$;
        RAISE NOTICE '227: tuned autovacuum for mol_silver.publications';
    ELSE
        RAISE NOTICE '227: mol_silver.publications does not exist, skipping';
    END IF;
END $$;

-- 2. mol_raw.chembl_activities
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'mol_raw' AND table_name = 'chembl_activities'
    ) THEN
        EXECUTE $sql$
            ALTER TABLE mol_raw.chembl_activities SET (
                autovacuum_vacuum_scale_factor = 0.02,
                autovacuum_analyze_scale_factor = 0.01,
                autovacuum_vacuum_cost_limit = 2000
            )
        $sql$;
        RAISE NOTICE '227: tuned autovacuum for mol_raw.chembl_activities';
    ELSE
        RAISE NOTICE '227: mol_raw.chembl_activities does not exist, skipping';
    END IF;
END $$;

-- 3. meta.transform_runs
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'meta' AND table_name = 'transform_runs'
    ) THEN
        EXECUTE $sql$
            ALTER TABLE meta.transform_runs SET (
                autovacuum_vacuum_scale_factor = 0.05,
                autovacuum_analyze_scale_factor = 0.01
            )
        $sql$;
        RAISE NOTICE '227: tuned autovacuum for meta.transform_runs';
    ELSE
        RAISE NOTICE '227: meta.transform_runs does not exist, skipping';
    END IF;
END $$;

-- 4. meta.api_audit_log
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'meta' AND table_name = 'api_audit_log'
    ) THEN
        EXECUTE $sql$
            ALTER TABLE meta.api_audit_log SET (
                autovacuum_vacuum_scale_factor = 0.05,
                autovacuum_analyze_scale_factor = 0.01
            )
        $sql$;
        RAISE NOTICE '227: tuned autovacuum for meta.api_audit_log';
    ELSE
        RAISE NOTICE '227: meta.api_audit_log does not exist, skipping';
    END IF;
END $$;

-- 5. mol_silver.bioactivity (conditional — may not exist yet)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'mol_silver' AND table_name = 'bioactivity'
    ) THEN
        EXECUTE $sql$
            ALTER TABLE mol_silver.bioactivity SET (
                autovacuum_vacuum_scale_factor = 0.02,
                autovacuum_analyze_scale_factor = 0.01,
                autovacuum_vacuum_cost_limit = 2000
            )
        $sql$;
        RAISE NOTICE '227: tuned autovacuum for mol_silver.bioactivity';
    ELSE
        RAISE NOTICE '227: mol_silver.bioactivity does not exist yet, will be tuned when created';
    END IF;
END $$;

DO $$
BEGIN
    RAISE NOTICE '227_autovacuum_per_table_tuning complete';
    RAISE NOTICE 'These settings are application-side — no infra ticket needed';
    RAISE NOTICE 'They complement (but do not replace) the planned Group B cluster params';
    RAISE NOTICE 'Verify: SELECT relname, reloptions FROM pg_class WHERE relname IN (''publications'', ''chembl_activities'', ''transform_runs'', ''api_audit_log'', ''bioactivity'')';
END $$;

COMMIT;
