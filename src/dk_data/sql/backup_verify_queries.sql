-- Backup sanity row-count verification queries
-- Feature: 001-silver-medallion-rebuild / T204
-- Run these after restoring a backup to verify data integrity.
-- Expected counts are approximate; adjust MIN_ROWS thresholds as the
-- dataset grows.  A restored database that passes all checks is
-- considered structurally sound.

-- ─── mol_raw (molecule raw ingestion) ────────────────────────────────────────
DO $$
DECLARE
    cnt bigint;
BEGIN
    SELECT COUNT(*) INTO cnt FROM mol_raw.chembl_activities;
    IF cnt < 1000 THEN
        RAISE EXCEPTION 'mol_raw.chembl_activities too small: % rows (min 1000)', cnt;
    END IF;
    RAISE NOTICE 'mol_raw.chembl_activities OK: % rows', cnt;

    SELECT COUNT(*) INTO cnt FROM mol_raw.chembl_molecules;
    IF cnt < 100 THEN
        RAISE EXCEPTION 'mol_raw.chembl_molecules too small: % rows (min 100)', cnt;
    END IF;
    RAISE NOTICE 'mol_raw.chembl_molecules OK: % rows', cnt;

    SELECT COUNT(*) INTO cnt FROM mol_raw.clinical_trials;
    IF cnt < 100 THEN
        RAISE EXCEPTION 'mol_raw.clinical_trials too small: % rows (min 100)', cnt;
    END IF;
    RAISE NOTICE 'mol_raw.clinical_trials OK: % rows', cnt;
END $$;

-- ─── ip_raw (intellectual property raw ingestion) ────────────────────────────
DO $$
DECLARE
    cnt bigint;
BEGIN
    SELECT COUNT(*) INTO cnt FROM ip_raw.uspto_patents;
    IF cnt < 10 THEN
        RAISE EXCEPTION 'ip_raw.uspto_patents too small: % rows (min 10)', cnt;
    END IF;
    RAISE NOTICE 'ip_raw.uspto_patents OK: % rows', cnt;

    SELECT COUNT(*) INTO cnt FROM ip_raw.euipo_trademarks;
    IF cnt < 10 THEN
        RAISE EXCEPTION 'ip_raw.euipo_trademarks too small: % rows (min 10)', cnt;
    END IF;
    RAISE NOTICE 'ip_raw.euipo_trademarks OK: % rows', cnt;
END $$;

-- ─── meta (platform metadata) ────────────────────────────────────────────────
DO $$
DECLARE
    cnt bigint;
BEGIN
    SELECT COUNT(*) INTO cnt FROM meta.data_sources;
    IF cnt < 1 THEN
        RAISE EXCEPTION 'meta.data_sources empty — backup may be corrupt', cnt;
    END IF;
    RAISE NOTICE 'meta.data_sources OK: % rows', cnt;

    -- job_runs may legitimately be empty in a fresh restore
    SELECT COUNT(*) INTO cnt FROM meta.job_runs;
    RAISE NOTICE 'meta.job_runs: % rows (informational)', cnt;
END $$;

-- ─── mol_bronze (molecule bronze layer) ──────────────────────────────────────
DO $$
DECLARE
    cnt bigint;
BEGIN
    SELECT COUNT(*) INTO cnt FROM mol_bronze.chembl_activities;
    IF cnt < 100 THEN
        RAISE EXCEPTION 'mol_bronze.chembl_activities too small: % rows (min 100)', cnt;
    END IF;
    RAISE NOTICE 'mol_bronze.chembl_activities OK: % rows', cnt;
END $$;

-- ─── mol_silver (molecule silver layer) ──────────────────────────────────────
DO $$
DECLARE
    cnt bigint;
BEGIN
    SELECT COUNT(*) INTO cnt FROM mol_silver.molecules;
    IF cnt < 10 THEN
        RAISE EXCEPTION 'mol_silver.molecules too small: % rows (min 10)', cnt;
    END IF;
    RAISE NOTICE 'mol_silver.molecules OK: % rows', cnt;
END $$;

-- ─── Schema presence guard ────────────────────────────────────────────────────
-- Verify all expected schemas exist (catches partial restores)
DO $$
DECLARE
    missing text;
BEGIN
    SELECT string_agg(s, ', ') INTO missing
    FROM unnest(ARRAY[
        'mol_raw', 'ip_raw', 'hcs_raw',
        'mol_bronze', 'ip_bronze',
        'mol_silver', 'ip_silver',
        'mol_gold', 'ip_gold',
        'meta', 'api', 'staging'
    ]) AS s
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.schemata
        WHERE schema_name = s
    );

    IF missing IS NOT NULL THEN
        RAISE EXCEPTION 'Missing schemas after restore: %', missing;
    END IF;
    RAISE NOTICE 'All required schemas present';
END $$;

-- ─── Row-count summary (informational) ───────────────────────────────────────
SELECT
    schemaname,
    tablename,
    n_live_tup AS estimated_rows
FROM pg_stat_user_tables
WHERE schemaname IN (
    'mol_raw', 'ip_raw', 'hcs_raw',
    'mol_bronze', 'ip_bronze',
    'mol_silver', 'ip_silver',
    'mol_gold', 'ip_gold',
    'meta'
)
ORDER BY schemaname, tablename;
