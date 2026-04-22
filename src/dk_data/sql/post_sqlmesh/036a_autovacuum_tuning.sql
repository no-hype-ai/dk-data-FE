-- Migration 031/036a: Per-table autovacuum tuning for heavy bronze tables
-- Feature: 001-silver-medallion-rebuild (audit fix 2026-04-12)
--
-- The cluster default autovacuum_vacuum_scale_factor=0.2 means autovacuum waits
-- until 20% of a table is dead tuples before triggering. On a 25M-row table that's
-- 5M dead rows — the resulting vacuum takes hours, locks the table for SAMPLE-mode
-- queries, and can produce GB of WAL during the cleanup pass.
--
-- For heavy append-mostly bronze tables we want autovacuum to run MORE often on
-- SMALLER amounts of dead data. Set scale_factor to 0.05 (5%) and a fixed threshold
-- of 50000 rows so it triggers reliably even when the table is small.
--
-- ANALYZE runs even more often (scale_factor 0.02) to keep the planner statistics
-- accurate during incremental loads — critical for the JSONB GIN indexes used by
-- bronze tables.
--
-- Per-table fillfactor stays at 100 (default) for append-mostly bronze tables.
-- For tables with frequent UPDATE (the upsert pattern in tray procs), set
-- fillfactor to 90 to leave 10% room for HOT updates and avoid index churn.

BEGIN;

-- ============================================================================
-- mol_bronze: heavy append-mostly tables
-- ============================================================================
DO $$
DECLARE
    v_table TEXT;
    v_tables TEXT[] := ARRAY[
        'mol_bronze.chembl_activities',
        'mol_bronze.bindingdb',
        'mol_bronze.clinicaltrials',
        'mol_bronze.pubchem',
        'mol_bronze.chembl_molecules',
        'mol_bronze.openfda_faers',
        'mol_bronze.openfda_labels',
        'mol_bronze.dailymed',
        'mol_bronze.pubmed',
        'mol_bronze.europepmc',
        'mol_bronze.drugbank',
        -- FDA medical devices (added 2026-04-21)
        'dev_bronze.openfda_device_510k',
        'dev_bronze.openfda_device_pma',
        'dev_bronze.openfda_device_classification',
        -- TGA Tier A (added 2026-04-21)
        'mol_bronze.tga_artg_medicines',
        'dev_bronze.tga_artg_devices',
        'mol_bronze.tga_sara_recalls',
        'mol_bronze.tga_medicine_shortages',
        'mol_bronze.tga_orphan_designations'
    ];
BEGIN
    FOREACH v_table IN ARRAY v_tables LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = split_part(v_table, '.', 1)
              AND table_name   = split_part(v_table, '.', 2)
        ) THEN
            EXECUTE format(
                'ALTER TABLE %s SET (
                    autovacuum_vacuum_scale_factor = 0.05,
                    autovacuum_vacuum_threshold = 50000,
                    autovacuum_analyze_scale_factor = 0.02,
                    autovacuum_analyze_threshold = 25000,
                    autovacuum_vacuum_cost_delay = 10,
                    fillfactor = 90
                )',
                v_table
            );
            RAISE NOTICE 'Tuned autovacuum on %', v_table;
        END IF;
    END LOOP;
END $$;

-- ============================================================================
-- hcs_bronze: large CMS PUF tables
-- ============================================================================
DO $$
DECLARE
    v_table TEXT;
    v_tables TEXT[] := ARRAY[
        'hcs_bronze.cms_inpatient_puf',
        'hcs_bronze.cms_outpatient_puf',
        'hcs_bronze.cms_open_payments',
        'hcs_bronze.cms_part_d_prescriber',
        'hcs_bronze.cms_npi',
        'hcs_bronze.cms_pecos',
        'hcs_bronze.cms_dme_puf',
        'hcs_bronze.cms_imaging_puf',
        'hcs_bronze.cms_lab_services',
        'hcs_bronze.cms_home_health',
        'hcs_bronze.cms_hospice_puf',
        'hcs_bronze.cms_snf_puf'
    ];
BEGIN
    FOREACH v_table IN ARRAY v_tables LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = split_part(v_table, '.', 1)
              AND table_name   = split_part(v_table, '.', 2)
        ) THEN
            EXECUTE format(
                'ALTER TABLE %s SET (
                    autovacuum_vacuum_scale_factor = 0.05,
                    autovacuum_vacuum_threshold = 50000,
                    autovacuum_analyze_scale_factor = 0.02,
                    autovacuum_analyze_threshold = 25000,
                    autovacuum_vacuum_cost_delay = 10,
                    fillfactor = 90
                )',
                v_table
            );
            RAISE NOTICE 'Tuned autovacuum on %', v_table;
        END IF;
    END LOOP;
END $$;

-- ============================================================================
-- ip_bronze + ip_raw: append-mostly patent/trademark data
-- ============================================================================
DO $$
DECLARE
    v_table TEXT;
    v_tables TEXT[] := ARRAY[
        'ip_bronze.uspto_patents',
        'ip_bronze.epo_patents',
        'ip_bronze.uspto_trademarks',
        'ip_raw.uspto_patents',
        'ip_raw.epo_patents',
        'ip_raw.uspto_trademarks'
    ];
BEGIN
    FOREACH v_table IN ARRAY v_tables LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = split_part(v_table, '.', 1)
              AND table_name   = split_part(v_table, '.', 2)
        ) THEN
            EXECUTE format(
                'ALTER TABLE %s SET (
                    autovacuum_vacuum_scale_factor = 0.05,
                    autovacuum_vacuum_threshold = 50000,
                    autovacuum_analyze_scale_factor = 0.02,
                    autovacuum_analyze_threshold = 25000,
                    autovacuum_vacuum_cost_delay = 10,
                    fillfactor = 100
                )',
                v_table
            );
            RAISE NOTICE 'Tuned autovacuum on %', v_table;
        END IF;
    END LOOP;
END $$;

-- ============================================================================
-- meta tables that grow continuously (transform_runs, slow_query_log, activity_log)
-- These see frequent INSERT and need more aggressive autovacuum to keep them lean
-- ============================================================================
DO $$
DECLARE
    v_table TEXT;
    v_tables TEXT[] := ARRAY[
        'meta.transform_runs',
        'meta.slow_query_log',
        'meta.activity_log',
        'meta.wal_status',
        'meta.wal_usage',
        'meta.job_runs'
    ];
BEGIN
    FOREACH v_table IN ARRAY v_tables LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = split_part(v_table, '.', 1)
              AND table_name   = split_part(v_table, '.', 2)
        ) THEN
            EXECUTE format(
                'ALTER TABLE %s SET (
                    autovacuum_vacuum_scale_factor = 0.1,
                    autovacuum_vacuum_threshold = 5000,
                    autovacuum_analyze_scale_factor = 0.05,
                    autovacuum_analyze_threshold = 2500
                )',
                v_table
            );
            RAISE NOTICE 'Tuned autovacuum on %', v_table;
        END IF;
    END LOOP;
END $$;

COMMIT;
