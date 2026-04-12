-- Migration 031/035: BRIN indexes on ingested_at/request_timestamp
-- Feature: 001-silver-medallion-rebuild / T160
--
-- Adds BRIN indexes on ingested_at/request_timestamp for the 5 heavy bronze tables.
-- Drops existing btree indexes on the same columns if they exist.
--
-- BRIN (Block Range INdex) is optimal for monotonically-increasing columns like
-- ingested_at: much smaller than btree, minimal WAL overhead, never bloats.

-- ----------------------------------------------------------------
-- mol_bronze.chembl_activities
-- ----------------------------------------------------------------
DROP INDEX IF EXISTS mol_bronze.idx_chembl_activities_ingested_at;
CREATE INDEX IF NOT EXISTS idx_chembl_activities_ingested_brin
    ON mol_bronze.chembl_activities USING BRIN (ingested_at)
    WITH (pages_per_range = 128);

-- ----------------------------------------------------------------
-- mol_bronze.bindingdb
-- ----------------------------------------------------------------
DROP INDEX IF EXISTS mol_bronze.idx_bindingdb_ingested_at;
CREATE INDEX IF NOT EXISTS idx_bindingdb_ingested_brin
    ON mol_bronze.bindingdb USING BRIN (ingested_at)
    WITH (pages_per_range = 128);

-- ----------------------------------------------------------------
-- mol_bronze.clinicaltrials
-- ----------------------------------------------------------------
DROP INDEX IF EXISTS mol_bronze.idx_clinicaltrials_ingested_at;
CREATE INDEX IF NOT EXISTS idx_clinicaltrials_ingested_brin
    ON mol_bronze.clinicaltrials USING BRIN (ingested_at)
    WITH (pages_per_range = 128);

-- ----------------------------------------------------------------
-- mol_bronze.pubchem
-- ----------------------------------------------------------------
DROP INDEX IF EXISTS mol_bronze.idx_pubchem_ingested_at;
CREATE INDEX IF NOT EXISTS idx_pubchem_ingested_brin
    ON mol_bronze.pubchem USING BRIN (ingested_at)
    WITH (pages_per_range = 128);

-- ----------------------------------------------------------------
-- mol_bronze.chembl_molecules
-- ----------------------------------------------------------------
DROP INDEX IF EXISTS mol_bronze.idx_chembl_molecules_ingested_at;
CREATE INDEX IF NOT EXISTS idx_chembl_molecules_ingested_brin
    ON mol_bronze.chembl_molecules USING BRIN (ingested_at)
    WITH (pages_per_range = 128);

-- ----------------------------------------------------------------
-- Large CMS tables (added per audit Bucket A.3)
-- ----------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'hcs_bronze' AND table_name = 'cms_inpatient_puf') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_cms_inpatient_puf_ingested_brin
                 ON hcs_bronze.cms_inpatient_puf USING BRIN (ingested_at) WITH (pages_per_range = 128)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'hcs_bronze' AND table_name = 'cms_outpatient_puf') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_cms_outpatient_puf_ingested_brin
                 ON hcs_bronze.cms_outpatient_puf USING BRIN (ingested_at) WITH (pages_per_range = 128)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'hcs_bronze' AND table_name = 'cms_open_payments') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_cms_open_payments_ingested_brin
                 ON hcs_bronze.cms_open_payments USING BRIN (ingested_at) WITH (pages_per_range = 128)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'mol_bronze' AND table_name = 'openfda_faers') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_openfda_faers_ingested_brin
                 ON mol_bronze.openfda_faers USING BRIN (ingested_at) WITH (pages_per_range = 128)';
    END IF;
END $$;
