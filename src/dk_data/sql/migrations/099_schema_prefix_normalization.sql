-- Migration 099: Schema prefix normalization
-- Ensures every table lives in a prefixed schema (mol_* or hcs_*).
-- No table is renamed — only the schema (namespace) changes.
--
-- Pattern:
--   raw.*       → mol_raw.*  (molecule raw ingestion)
--   raw.*       → hcs_raw.*  (healthcare/facility raw ingestion)
--   bronze.*    → mol_bronze.* or hcs_bronze.*
--   mol_silver.*    → mol_silver.* or hcs_silver.*
--   mol_gold.*      → mol_gold.*  (if any remained unprefixed)
--
-- Idempotent: skips any move where the source does not exist in the old schema
-- OR the target already exists in the new schema (tables may have been created
-- directly in mol_raw by later migrations).

BEGIN;

-- Helper: move a table only when source exists AND target does not.
-- Usage: SELECT _safe_move_schema('raw', 'tablename', 'mol_raw');
CREATE OR REPLACE FUNCTION _safe_move_schema(
    src_schema TEXT, tbl TEXT, dst_schema TEXT
) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = src_schema AND tablename = tbl)
       AND NOT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = dst_schema AND tablename = tbl)
    THEN
        EXECUTE format('ALTER TABLE %I.%I SET SCHEMA %I', src_schema, tbl, dst_schema);
    END IF;
END;
$$;

-- ============================================================
-- RAW → mol_raw  (molecule data sources)
-- ============================================================
SELECT _safe_move_schema('raw', 'bindingdb',         'mol_raw');
SELECT _safe_move_schema('raw', 'chembl',             'mol_raw');
SELECT _safe_move_schema('raw', 'clinicaltrials',     'mol_raw');
SELECT _safe_move_schema('raw', 'cochrane_reviews',   'mol_raw');
SELECT _safe_move_schema('raw', 'drugbank',           'mol_raw');
SELECT _safe_move_schema('raw', 'ema',                'mol_raw');
SELECT _safe_move_schema('raw', 'epo_patents',        'mol_raw');
SELECT _safe_move_schema('raw', 'euipo_trademarks',   'mol_raw');
SELECT _safe_move_schema('raw', 'hta_decisions',      'mol_raw');
SELECT _safe_move_schema('raw', 'journal_rss',        'mol_raw');
SELECT _safe_move_schema('raw', 'medical_news',       'mol_raw');
SELECT _safe_move_schema('raw', 'openalex_ci',        'mol_raw');
SELECT _safe_move_schema('raw', 'openfda_faers',      'mol_raw');
SELECT _safe_move_schema('raw', 'openfda_labels',     'mol_raw');
SELECT _safe_move_schema('raw', 'orange_book',        'mol_raw');
SELECT _safe_move_schema('raw', 'orcid',              'mol_raw');
SELECT _safe_move_schema('raw', 'pdb',                'mol_raw');
SELECT _safe_move_schema('raw', 'pubchem',            'mol_raw');
SELECT _safe_move_schema('raw', 'pubmed',             'mol_raw');
SELECT _safe_move_schema('raw', 'sec_edgar',          'mol_raw');
SELECT _safe_move_schema('raw', 'sider',              'mol_raw');
SELECT _safe_move_schema('raw', 'uniprot',            'mol_raw');
SELECT _safe_move_schema('raw', 'uspto_ci',           'mol_raw');
SELECT _safe_move_schema('raw', 'uspto_patents',      'mol_raw');
SELECT _safe_move_schema('raw', 'uspto_trademarks',   'mol_raw');
SELECT _safe_move_schema('raw', 'who_icd',            'mol_raw');

-- ============================================================
-- RAW → hcs_raw  (healthcare / facility data sources)
-- ============================================================
SELECT _safe_move_schema('raw', 'acc_tvc_certification',   'hcs_raw');
SELECT _safe_move_schema('raw', 'cms_cost_reports',        'hcs_raw');
SELECT _safe_move_schema('raw', 'cms_hospital_info',       'hcs_raw');
SELECT _safe_move_schema('raw', 'cms_medicare_inpatient',  'hcs_raw');
SELECT _safe_move_schema('raw', 'cms_geographic_variation','hcs_raw');
SELECT _safe_move_schema('raw', 'hrsa_shortage_areas',     'hcs_raw');

-- ============================================================
-- BRONZE → mol_bronze  (molecule bronze tables)
-- ============================================================
SELECT _safe_move_schema('bronze', 'bindingdb',          'mol_bronze');
SELECT _safe_move_schema('bronze', 'chembl_molecules',   'mol_bronze');
SELECT _safe_move_schema('bronze', 'clinicaltrials',     'mol_bronze');
SELECT _safe_move_schema('bronze', 'cochrane_reviews',   'mol_bronze');
SELECT _safe_move_schema('bronze', 'drugbank',           'mol_bronze');
SELECT _safe_move_schema('bronze', 'ema',                'mol_bronze');
SELECT _safe_move_schema('bronze', 'epo_patents',        'mol_bronze');
SELECT _safe_move_schema('bronze', 'euipo_trademarks',   'mol_bronze');
SELECT _safe_move_schema('bronze', 'europepmc',          'mol_bronze');
SELECT _safe_move_schema('bronze', 'faers_events',       'mol_bronze');
SELECT _safe_move_schema('bronze', 'hta_decisions',      'mol_bronze');
SELECT _safe_move_schema('bronze', 'journal_rss',        'mol_bronze');
SELECT _safe_move_schema('bronze', 'medical_news',       'mol_bronze');
SELECT _safe_move_schema('bronze', 'openalex',           'mol_bronze');
SELECT _safe_move_schema('bronze', 'openfda_labels',     'mol_bronze');
SELECT _safe_move_schema('bronze', 'orange_book',        'mol_bronze');
SELECT _safe_move_schema('bronze', 'orcid',              'mol_bronze');
SELECT _safe_move_schema('bronze', 'pdb_structures',     'mol_bronze');
SELECT _safe_move_schema('bronze', 'pubchem',            'mol_bronze');
SELECT _safe_move_schema('bronze', 'pubmed',             'mol_bronze');
SELECT _safe_move_schema('bronze', 'sec_edgar',          'mol_bronze');
SELECT _safe_move_schema('bronze', 'sider',              'mol_bronze');
SELECT _safe_move_schema('bronze', 'uniprot',            'mol_bronze');
SELECT _safe_move_schema('bronze', 'uspto_ci',           'mol_bronze');
SELECT _safe_move_schema('bronze', 'uspto_patents',      'mol_bronze');
SELECT _safe_move_schema('bronze', 'uspto_trademarks',   'mol_bronze');
SELECT _safe_move_schema('bronze', 'who_icd',            'mol_bronze');

-- ============================================================
-- BRONZE → hcs_bronze  (healthcare / facility bronze tables)
-- ============================================================
SELECT _safe_move_schema('bronze', 'acc_tvc',                  'hcs_bronze');
SELECT _safe_move_schema('bronze', 'cms_cost_reports',         'hcs_bronze');
SELECT _safe_move_schema('bronze', 'cms_hospital_info',        'hcs_bronze');
SELECT _safe_move_schema('bronze', 'cms_inpatient',            'hcs_bronze');
SELECT _safe_move_schema('bronze', 'cms_geographic_variation', 'hcs_bronze');
SELECT _safe_move_schema('bronze', 'hrsa',                     'hcs_bronze');

-- ============================================================
-- SILVER → mol_silver  (mol_silver self-moves are no-ops; cross-domain moves below)
-- ============================================================
-- (No mol_silver → mol_silver moves needed — tables already live there)

-- ============================================================
-- SILVER → hcs_silver  (healthcare / facility silver tables)
-- ============================================================
SELECT _safe_move_schema('mol_silver', 'geographic_health',     'hcs_silver');
SELECT _safe_move_schema('mol_silver', 'healthcare_facilities', 'hcs_silver');

-- Clean up helper function
DROP FUNCTION IF EXISTS _safe_move_schema(TEXT, TEXT, TEXT);

COMMIT;
