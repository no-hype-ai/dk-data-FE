-- Migration 031/000a: Gold-layer indexes
-- Feature: 001-silver-medallion-rebuild (audit fix 2026-04-12)
--
-- Gold tables are created by SQLMesh, not by migrations. On first deploy they
-- may not exist yet. Each index is wrapped in _try_create_index() which catches
-- undefined_table and skips gracefully. Indexes that were skipped will be created
-- on the next deploy after SQLMesh has materialized the tables.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE OR REPLACE FUNCTION _try_create_index(p_ddl text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    EXECUTE p_ddl;
EXCEPTION WHEN undefined_table THEN
    RAISE NOTICE 'Skipping (table not yet created by SQLMesh): %', left(p_ddl, 120);
END;
$$;

-- ============================================================================
-- mol_gold
-- ============================================================================
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS mol_gold_advocacy_groups_pk_idx ON mol_gold.advocacy_groups (group_id)');
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS mol_gold_advocacy_sentiment_pk_idx ON mol_gold.advocacy_sentiment (molecule_id, source)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS mol_gold_advocacy_sentiment_mol_idx ON mol_gold.advocacy_sentiment (molecule_id)');
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS mol_gold_financial_summary_pk_idx ON mol_gold.financial_summary (molecule_id, cik)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS mol_gold_financial_summary_mol_idx ON mol_gold.financial_summary (molecule_id)');
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS mol_gold_kol_drug_assoc_pk_idx ON mol_gold.kol_drug_associations (researcher_id, molecule_id)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS mol_gold_kol_drug_assoc_mol_idx ON mol_gold.kol_drug_associations (molecule_id)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS mol_gold_kol_drug_assoc_res_idx ON mol_gold.kol_drug_associations (researcher_id)');
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS mol_gold_kol_network_pk_idx ON mol_gold.kol_network (source_researcher_id, target_researcher_id)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS mol_gold_kol_network_src_idx ON mol_gold.kol_network (source_researcher_id)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS mol_gold_kol_network_tgt_idx ON mol_gold.kol_network (target_researcher_id)');
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS mol_gold_kol_profiles_pk_idx ON mol_gold.kol_profiles (researcher_id)');
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS mol_gold_lifecycle_evidence_pk_idx ON mol_gold.lifecycle_evidence (molecule_id, evidence_type, evidence_id)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS mol_gold_lifecycle_evidence_mol_idx ON mol_gold.lifecycle_evidence (molecule_id)');
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS mol_gold_market_summary_pk_idx ON mol_gold.market_summary (molecule_id)');
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS mol_gold_regulatory_timeline_pk_idx ON mol_gold.regulatory_timeline (molecule_id, agency, decision_date)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS mol_gold_regulatory_timeline_mol_idx ON mol_gold.regulatory_timeline (molecule_id)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS mol_gold_molecule_profile_inchi_idx ON mol_gold.molecule_profile (inchi_key)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS mol_gold_molecule_profile_canon_trgm_idx ON mol_gold.molecule_profile USING GIN (LOWER(canonical_name) gin_trgm_ops)');

-- ============================================================================
-- hcs_gold
-- ============================================================================
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS hcs_gold_cms_facility_360_pk_idx ON hcs_gold.cms_facility_360 (ccn)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS hcs_gold_cms_facility_360_state_idx ON hcs_gold.cms_facility_360 (state)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS hcs_gold_cms_facility_360_facility_name_trgm_idx ON hcs_gold.cms_facility_360 USING GIN (LOWER(facility_name) gin_trgm_ops)');
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS hcs_gold_cms_provider_360_pk_idx ON hcs_gold.cms_provider_360 (npi)');
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS hcs_gold_facility_master_pk_idx ON hcs_gold.facility_master (provider_id)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS hcs_gold_facility_master_state_idx ON hcs_gold.facility_master (state)');
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS hcs_gold_nucc_taxonomy_pk_idx ON hcs_gold.nucc_taxonomy (taxonomy_code)');
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS hcs_gold_cms_market_analytics_pk_idx ON hcs_gold.cms_market_analytics (geo_code, geo_level)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS hcs_gold_cms_market_analytics_geo_idx ON hcs_gold.cms_market_analytics (geo_code)');
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS hcs_gold_cms_drug_market_pk_idx ON hcs_gold.cms_drug_market_profile (generic_name, _source_year)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS hcs_gold_cms_drug_market_generic_idx ON hcs_gold.cms_drug_market_profile (generic_name)');
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS hcs_gold_npi_prescribing_pk_idx ON hcs_gold.npi_prescribing (molecule_id, gnrc_name, _source_year)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS hcs_gold_npi_prescribing_mol_idx ON hcs_gold.npi_prescribing (molecule_id)');
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS hcs_gold_prescriber_payments_pk_idx ON hcs_gold.prescriber_payments (molecule_id, applicable_manufacturer_or_gpo_name, _source_year)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS hcs_gold_prescriber_payments_mol_idx ON hcs_gold.prescriber_payments (molecule_id)');

-- ============================================================================
-- ind_gold
-- ============================================================================
SELECT _try_create_index('CREATE UNIQUE INDEX IF NOT EXISTS ind_gold_indication_catalog_pk_idx ON ind_gold.indication_catalog (icd11_code)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS ind_gold_indication_catalog_ta_idx ON ind_gold.indication_catalog (therapeutic_area)');

DROP FUNCTION _try_create_index(text);

COMMIT;
