-- Migration 031/035: BRIN indexes on ingested_at/request_timestamp
-- Feature: 001-silver-medallion-rebuild / T160
--
-- BRIN (Block Range INdex) is optimal for monotonically-increasing columns like
-- ingested_at: much smaller than btree, minimal WAL overhead, never bloats.
--
-- Bronze tables are created by SQLMesh, not migrations. On first deploy they may
-- not exist yet. Each statement is wrapped defensively to skip gracefully.

BEGIN;

CREATE OR REPLACE FUNCTION _try_brin_index(p_drop_ddl text, p_create_ddl text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    EXECUTE p_drop_ddl;
    EXECUTE p_create_ddl;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Skipping BRIN (table/schema not yet created): %', left(p_create_ddl, 120);
END;
$$;

-- mol_bronze heavy tables
SELECT _try_brin_index(
    'DROP INDEX IF EXISTS mol_bronze.idx_chembl_activities_ingested_at',
    'CREATE INDEX IF NOT EXISTS idx_chembl_activities_ingested_brin ON mol_bronze.chembl_activities USING BRIN (ingested_at) WITH (pages_per_range = 128)');

SELECT _try_brin_index(
    'DROP INDEX IF EXISTS mol_bronze.idx_bindingdb_ingested_at',
    'CREATE INDEX IF NOT EXISTS idx_bindingdb_ingested_brin ON mol_bronze.bindingdb USING BRIN (ingested_at) WITH (pages_per_range = 128)');

SELECT _try_brin_index(
    'DROP INDEX IF EXISTS mol_bronze.idx_clinicaltrials_ingested_at',
    'CREATE INDEX IF NOT EXISTS idx_clinicaltrials_ingested_brin ON mol_bronze.clinicaltrials USING BRIN (ingested_at) WITH (pages_per_range = 128)');

SELECT _try_brin_index(
    'DROP INDEX IF EXISTS mol_bronze.idx_pubchem_ingested_at',
    'CREATE INDEX IF NOT EXISTS idx_pubchem_ingested_brin ON mol_bronze.pubchem USING BRIN (ingested_at) WITH (pages_per_range = 128)');

SELECT _try_brin_index(
    'DROP INDEX IF EXISTS mol_bronze.idx_chembl_molecules_ingested_at',
    'CREATE INDEX IF NOT EXISTS idx_chembl_molecules_ingested_brin ON mol_bronze.chembl_molecules USING BRIN (ingested_at) WITH (pages_per_range = 128)');

-- Large CMS tables (may or may not exist)
SELECT _try_brin_index(
    'SELECT 1',
    'CREATE INDEX IF NOT EXISTS idx_cms_inpatient_puf_ingested_brin ON hcs_bronze.cms_inpatient_puf USING BRIN (ingested_at) WITH (pages_per_range = 128)');

SELECT _try_brin_index(
    'SELECT 1',
    'CREATE INDEX IF NOT EXISTS idx_cms_outpatient_puf_ingested_brin ON hcs_bronze.cms_outpatient_puf USING BRIN (ingested_at) WITH (pages_per_range = 128)');

SELECT _try_brin_index(
    'SELECT 1',
    'CREATE INDEX IF NOT EXISTS idx_cms_open_payments_ingested_brin ON hcs_bronze.cms_open_payments USING BRIN (ingested_at) WITH (pages_per_range = 128)');

SELECT _try_brin_index(
    'SELECT 1',
    'CREATE INDEX IF NOT EXISTS idx_openfda_faers_ingested_brin ON mol_bronze.openfda_faers USING BRIN (ingested_at) WITH (pages_per_range = 128)');

DROP FUNCTION _try_brin_index(text, text);

COMMIT;
