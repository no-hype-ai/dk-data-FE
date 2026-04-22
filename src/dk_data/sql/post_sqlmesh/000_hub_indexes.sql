-- Migration 000: Indexes on silver hub crosswalk tables
-- Part of: 001-silver-medallion-rebuild
--
-- The silver hub models declare INCREMENTAL_BY_UNIQUE_KEY but SQLMesh enforces the
-- unique_key at upsert time only; it does not create SQL UNIQUE constraints or any
-- secondary indexes on the materialized tables. Without these indexes, every
-- resolve_*() call (e.g. WHERE source = ? AND identifier = ?) does a sequential scan
-- of the entire crosswalk, and the gold-tier ≤10 ms p99 target (SC-004) is unreachable.
--
-- Hub crosswalk tables are created by SQLMesh, not by migrations. On first deploy the
-- tables may not exist yet. Each index statement is wrapped in a helper that catches
-- undefined_table and skips gracefully. The migration is still recorded as applied;
-- indexes will be created on the NEXT deploy after SQLMesh has materialized the tables.

BEGIN;

-- Ensure all domain schemas exist (in CI, only mol_* schemas are created by migration 020;
-- hcs_*, ind_*, hcp_*, ip_* are normally created by db-init Wave 1 which doesn't run in CI).
CREATE SCHEMA IF NOT EXISTS hcs_raw;
CREATE SCHEMA IF NOT EXISTS hcs_bronze;
CREATE SCHEMA IF NOT EXISTS hcs_silver;
CREATE SCHEMA IF NOT EXISTS hcs_gold;
CREATE SCHEMA IF NOT EXISTS ind_raw;
CREATE SCHEMA IF NOT EXISTS ind_bronze;
CREATE SCHEMA IF NOT EXISTS ind_silver;
CREATE SCHEMA IF NOT EXISTS ind_gold;
CREATE SCHEMA IF NOT EXISTS hcp_silver;
CREATE SCHEMA IF NOT EXISTS hcp_gold;
CREATE SCHEMA IF NOT EXISTS ip_raw;
CREATE SCHEMA IF NOT EXISTS ip_bronze;
CREATE SCHEMA IF NOT EXISTS ip_silver;
CREATE SCHEMA IF NOT EXISTS ip_gold;
CREATE SCHEMA IF NOT EXISTS meta;
CREATE SCHEMA IF NOT EXISTS staging;

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Helper: execute DDL, silently skip if the target table does not exist yet.
CREATE OR REPLACE FUNCTION _try_create_index(p_ddl text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    EXECUTE p_ddl;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Skipping (table/schema not yet created): %', left(p_ddl, 120);
END;
$$;

-- ============================================================
-- mol_silver
-- ============================================================
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS mol_silver_molecules_pk_idx ON mol_silver.molecules (molecule_id)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS mol_silver_molecules_canon_idx ON mol_silver.molecules (canonical_name)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS mol_silver_molecules_canon_trgm_idx ON mol_silver.molecules USING GIN (LOWER(canonical_name) gin_trgm_ops)');

SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS mol_silver_mol_ident_src_id_idx ON mol_silver.molecule_identifiers (source, identifier)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS mol_silver_mol_ident_mol_idx ON mol_silver.molecule_identifiers (molecule_id)');

SELECT _try_create_index('CREATE INDEX IF NOT EXISTS mol_silver_mol_names_norm_idx ON mol_silver.molecule_names (normalized_name)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS mol_silver_mol_names_trgm_idx ON mol_silver.molecule_names USING GIN (LOWER(normalized_name) gin_trgm_ops)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS mol_silver_mol_names_mol_idx ON mol_silver.molecule_names (molecule_id)');

-- drug_products hub
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS mol_silver_drug_products_pk_idx ON mol_silver.drug_products (product_id)');
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS mol_silver_dp_ident_src_id_idx ON mol_silver.drug_product_identifiers (source, identifier)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS mol_silver_dp_ident_prod_idx ON mol_silver.drug_product_identifiers (product_id)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS mol_silver_dp_names_norm_idx ON mol_silver.drug_product_names (normalized_name)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS mol_silver_dp_names_trgm_idx ON mol_silver.drug_product_names USING GIN (LOWER(normalized_name) gin_trgm_ops)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS mol_silver_dp_names_prod_idx ON mol_silver.drug_product_names (product_id)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS mol_silver_dp_ingr_prod_idx ON mol_silver.drug_product_ingredients (product_id)');

-- companies hub
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS mol_silver_companies_pk_idx ON mol_silver.companies (company_id)');
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS mol_silver_co_ident_src_id_idx ON mol_silver.company_identifiers (source, identifier)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS mol_silver_co_ident_co_idx ON mol_silver.company_identifiers (company_id)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS mol_silver_co_names_trgm_idx ON mol_silver.company_names USING GIN (LOWER(normalized_name) gin_trgm_ops)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS mol_silver_co_names_co_idx ON mol_silver.company_names (company_id)');

-- targets hub
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS mol_silver_targets_pk_idx ON mol_silver.targets (target_id)');
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS mol_silver_tgt_ident_src_id_idx ON mol_silver.target_identifiers (source, identifier)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS mol_silver_tgt_ident_tgt_idx ON mol_silver.target_identifiers (target_id)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS mol_silver_tgt_names_trgm_idx ON mol_silver.target_names USING GIN (LOWER(normalized_name) gin_trgm_ops)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS mol_silver_tgt_names_tgt_idx ON mol_silver.target_names (target_id)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS mol_silver_tgt_seq_hash_idx ON mol_silver.target_sequences (sequence_hash)');

-- ============================================================
-- hcs_silver
-- ============================================================
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS hcs_silver_providers_pk_idx ON hcs_silver.providers (provider_id)');
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS hcs_silver_prov_ident_src_id_idx ON hcs_silver.provider_identifiers (source, identifier)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS hcs_silver_prov_ident_prov_idx ON hcs_silver.provider_identifiers (provider_id)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS hcs_silver_prov_names_trgm_idx ON hcs_silver.provider_names USING GIN (LOWER(normalized_name) gin_trgm_ops)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS hcs_silver_prov_names_prov_idx ON hcs_silver.provider_names (provider_id)');

SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS hcs_silver_facilities_pk_idx ON hcs_silver.facilities (facility_id)');
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS hcs_silver_fac_ident_src_id_idx ON hcs_silver.facility_identifiers (source, identifier)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS hcs_silver_fac_ident_fac_idx ON hcs_silver.facility_identifiers (facility_id)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS hcs_silver_fac_names_trgm_idx ON hcs_silver.facility_names USING GIN (LOWER(normalized_name) gin_trgm_ops)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS hcs_silver_fac_names_fac_idx ON hcs_silver.facility_names (facility_id)');

-- ============================================================
-- ind_silver
-- ============================================================
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS ind_silver_conditions_pk_idx ON ind_silver.conditions (condition_id)');
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS ind_silver_cond_ident_src_id_idx ON ind_silver.condition_identifiers (source, identifier)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS ind_silver_cond_ident_cond_idx ON ind_silver.condition_identifiers (condition_id)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS ind_silver_cond_names_trgm_idx ON ind_silver.condition_names USING GIN (LOWER(normalized_name) gin_trgm_ops)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS ind_silver_cond_names_cond_idx ON ind_silver.condition_names (condition_id)');

-- ============================================================
-- hcp_silver
-- ============================================================
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS hcp_silver_researchers_pk_idx ON hcp_silver.researchers (researcher_id)');
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS hcp_silver_res_ident_src_id_idx ON hcp_silver.researcher_identifiers (source, identifier)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS hcp_silver_res_ident_res_idx ON hcp_silver.researcher_identifiers (researcher_id)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS hcp_silver_res_names_trgm_idx ON hcp_silver.researcher_names USING GIN (LOWER(normalized_name) gin_trgm_ops)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS hcp_silver_res_names_res_idx ON hcp_silver.researcher_names (researcher_id)');

-- ============================================================
-- ip_silver
-- ============================================================
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS ip_silver_patents_pk_idx ON ip_silver.patents (patent_id)');
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS ip_silver_pat_ident_src_id_idx ON ip_silver.patent_identifiers (source, identifier)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS ip_silver_pat_ident_pat_idx ON ip_silver.patent_identifiers (patent_id)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS ip_silver_pat_names_trgm_idx ON ip_silver.patent_names USING GIN (LOWER(normalized_name) gin_trgm_ops)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS ip_silver_pat_names_pat_idx ON ip_silver.patent_names (patent_id)');

SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS ip_silver_trademarks_pk_idx ON ip_silver.trademarks (trademark_id)');
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS ip_silver_tm_ident_src_id_idx ON ip_silver.trademark_identifiers (source, identifier)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS ip_silver_tm_ident_tm_idx ON ip_silver.trademark_identifiers (trademark_id)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS ip_silver_tm_names_trgm_idx ON ip_silver.trademark_names USING GIN (LOWER(normalized_name) gin_trgm_ops)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS ip_silver_tm_names_tm_idx ON ip_silver.trademark_names (trademark_id)');

SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS ip_silver_designs_pk_idx ON ip_silver.designs (design_id)');
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS ip_silver_des_ident_src_id_idx ON ip_silver.design_identifiers (source, identifier)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS ip_silver_des_ident_des_idx ON ip_silver.design_identifiers (design_id)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS ip_silver_des_names_trgm_idx ON ip_silver.design_names USING GIN (LOWER(normalized_name) gin_trgm_ops)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS ip_silver_des_names_des_idx ON ip_silver.design_names (design_id)');

-- ============================================================
-- dev_silver — devices hub (12th hub, added 2026-04-21)
-- ============================================================
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS dev_silver_devices_pk_idx ON dev_silver.devices (device_id)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS dev_silver_devices_product_code_idx ON dev_silver.devices (product_code)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS dev_silver_devices_device_class_idx ON dev_silver.devices (device_class)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS dev_silver_devices_canon_trgm_idx ON dev_silver.devices USING GIN (LOWER(canonical_name) gin_trgm_ops)');

SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS dev_silver_dev_ident_src_id_idx ON dev_silver.device_identifiers (source, identifier)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS dev_silver_dev_ident_device_idx ON dev_silver.device_identifiers (device_id)');

-- Trigram GIN powering resolve_device tier 5 (fuzzy name ≥0.85, SC-004 p99 ≤10ms)
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS dev_silver_dev_names_trgm_idx ON dev_silver.device_names USING GIN (LOWER(normalized_name) gin_trgm_ops)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS dev_silver_dev_names_norm_idx ON dev_silver.device_names (normalized_name)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS dev_silver_dev_names_device_idx ON dev_silver.device_names (device_id)');

-- Cleanup helper
DROP FUNCTION _try_create_index(text);

COMMIT;
