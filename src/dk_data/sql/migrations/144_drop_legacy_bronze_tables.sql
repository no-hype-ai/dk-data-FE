-- Migration 144: Drop legacy physical tables that conflict with SQLMesh virtual views
--
-- Problem: Early migrations (020, 029, 050, 080, 099, and many silver/gold DDL
-- migrations) created physical TABLES in mol_bronze, mol_silver, and mol_gold.
-- SQLMesh now manages the entire medallion stack (bronze/silver/gold) as virtual
-- VIEWS over mol_raw.*. When SQLMesh tries to create/replace a VIEW, PostgreSQL
-- raises:
--   "ERROR: <table> is not a view"
-- because DROP VIEW IF EXISTS fails when the named object is a TABLE.
--
-- Fix: Drop the legacy physical tables that conflict with SQLMesh-managed views.
-- The data pipeline uses mol_raw.* as the source of truth; mol_bronze/silver/gold
-- are the SQLMesh virtual transformation layers, not storage layers.
--
-- CASCADE: handles any dependent views or materialized views.
-- IF EXISTS guard (via pg_tables check): idempotent, safe to re-run.

BEGIN;

DO $$
DECLARE
    tbl TEXT;
BEGIN
    -- -------------------------------------------------------------------------
    -- mol_bronze: tables moved from bronze → mol_bronze by migration 099
    -- (created by migrations 029, 050, 080) that conflict with SQLMesh views
    -- -------------------------------------------------------------------------
    FOREACH tbl IN ARRAY ARRAY[
        'pubmed', 'uniprot', 'openalex', 'ema', 'orange_book',
        'bindingdb', 'cochrane_reviews', 'epo_patents', 'euipo_trademarks',
        'europepmc', 'faers_events', 'hta_decisions', 'journal_rss',
        'medical_news', 'orcid', 'pdb_structures', 'sec_edgar', 'sider',
        'uspto_ci', 'uspto_patents', 'uspto_trademarks', 'who_icd'
    ] LOOP
        IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'mol_bronze' AND tablename = tbl) THEN
            EXECUTE format('DROP TABLE mol_bronze.%I CASCADE', tbl);
            RAISE NOTICE 'Dropped mol_bronze.%', tbl;
        END IF;
    END LOOP;

    -- mol_bronze: tables created directly in mol_bronze by migration 020
    FOREACH tbl IN ARRAY ARRAY[
        'clinicaltrials', 'pubchem', 'drugbank', 'openfda_labels', 'openfda_faers'
    ] LOOP
        IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'mol_bronze' AND tablename = tbl) THEN
            EXECUTE format('DROP TABLE mol_bronze.%I CASCADE', tbl);
            RAISE NOTICE 'Dropped mol_bronze.%', tbl;
        END IF;
    END LOOP;

    -- -------------------------------------------------------------------------
    -- mol_silver: physical tables created by silver DDL migrations that conflict
    -- with SQLMesh-managed virtual views
    -- -------------------------------------------------------------------------
    FOREACH tbl IN ARRAY ARRAY[
        'adverse_events', 'bioactivity', 'clinical_trials', 'company_financials',
        'drug_labels', 'drug_pharmacology', 'hcpcs_molecule_bridge',
        'identifier_mappings', 'molecule_aliases', 'molecule_publications',
        'molecule_targets', 'molecules', 'ndc_molecule_bridge', 'patents',
        'pharmacogenomics', 'physician_payments', 'protein_structures',
        'proteins', 'publication_evidence', 'publications', 'research_grants',
        'targets'
    ] LOOP
        IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'mol_silver' AND tablename = tbl) THEN
            EXECUTE format('DROP TABLE mol_silver.%I CASCADE', tbl);
            RAISE NOTICE 'Dropped mol_silver.%', tbl;
        END IF;
    END LOOP;

    -- -------------------------------------------------------------------------
    -- mol_gold: physical tables created by gold DDL migrations that conflict
    -- with SQLMesh-managed virtual views
    -- -------------------------------------------------------------------------
    FOREACH tbl IN ARRAY ARRAY[
        'competitive_landscape', 'lifecycle_stages', 'molecule_profile',
        'safety_signals', 'trial_outcomes', 'company_pipeline'
    ] LOOP
        IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'mol_gold' AND tablename = tbl) THEN
            EXECUTE format('DROP TABLE mol_gold.%I CASCADE', tbl);
            RAISE NOTICE 'Dropped mol_gold.%', tbl;
        END IF;
    END LOOP;
END $$;

DO $$ BEGIN
    RAISE NOTICE 'Migration 144 complete: legacy medallion physical tables dropped.';
    RAISE NOTICE 'SQLMesh virtual views can now be created across mol_bronze/silver/gold.';
END $$;

COMMIT;
