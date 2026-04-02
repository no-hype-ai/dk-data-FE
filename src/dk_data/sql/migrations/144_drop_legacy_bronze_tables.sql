-- Migration 144: Drop legacy mol_bronze physical tables managed by SQLMesh
--
-- Problem: Migrations 020, 029, 050, 080, and 099 created physical TABLES in
-- mol_bronze (or bronze, then moved to mol_bronze). SQLMesh now manages the
-- entire bronze medallion layer as virtual VIEWS over mol_raw.*. When SQLMesh
-- tries to create/replace a VIEW in mol_bronze, PostgreSQL raises:
--   "ERROR: <table> is not a view"
-- because DROP VIEW IF EXISTS fails if the named object is a TABLE.
--
-- Fix: Drop the legacy physical tables that now conflict with SQLMesh-managed
-- virtual views. The data pipeline uses mol_raw.* as the source of truth;
-- mol_bronze.* is the SQLMesh virtual layer, not a storage layer.
--
-- CASCADE: handles any dependent views or materialized views.
-- IF EXISTS guard (via pg_tables check): safe to re-run if already dropped.

BEGIN;

DO $$
DECLARE
    tbl TEXT;
BEGIN
    -- Tables moved from bronze → mol_bronze by migration 099 that conflict
    -- with SQLMesh virtual views (created by migrations 029, 050, 080)
    FOREACH tbl IN ARRAY ARRAY[
        'pubmed',
        'uniprot',
        'openalex',
        'ema',
        'orange_book',
        'bindingdb',
        'cochrane_reviews',
        'epo_patents',
        'euipo_trademarks',
        'europepmc',
        'faers_events',
        'hta_decisions',
        'journal_rss',
        'medical_news',
        'orcid',
        'pdb_structures',
        'sec_edgar',
        'sider',
        'uspto_ci',
        'uspto_patents',
        'uspto_trademarks',
        'who_icd'
    ] LOOP
        IF EXISTS (
            SELECT 1 FROM pg_tables
            WHERE schemaname = 'mol_bronze' AND tablename = tbl
        ) THEN
            EXECUTE format('DROP TABLE mol_bronze.%I CASCADE', tbl);
            RAISE NOTICE 'Dropped legacy table mol_bronze.%', tbl;
        END IF;
    END LOOP;

    -- Tables created directly in mol_bronze by migration 020 that conflict
    -- with SQLMesh virtual views
    FOREACH tbl IN ARRAY ARRAY[
        'clinicaltrials',
        'pubchem',
        'drugbank',
        'openfda_labels',
        'openfda_faers'
    ] LOOP
        IF EXISTS (
            SELECT 1 FROM pg_tables
            WHERE schemaname = 'mol_bronze' AND tablename = tbl
        ) THEN
            EXECUTE format('DROP TABLE mol_bronze.%I CASCADE', tbl);
            RAISE NOTICE 'Dropped legacy table mol_bronze.%', tbl;
        END IF;
    END LOOP;
END $$;

DO $$ BEGIN
    RAISE NOTICE 'Migration 144 complete: legacy mol_bronze physical tables dropped.';
    RAISE NOTICE 'SQLMesh virtual views can now be created in mol_bronze.';
END $$;

COMMIT;
