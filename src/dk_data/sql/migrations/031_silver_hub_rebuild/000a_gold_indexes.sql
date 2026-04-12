-- Migration 031/000a: Gold-layer indexes
-- Feature: 001-silver-medallion-rebuild (audit fix 2026-04-12)
--
-- SQLMesh's INCREMENTAL_BY_UNIQUE_KEY only enforces the unique_key at upsert time
-- via MERGE — it does NOT create a Postgres unique index. That means PostgREST and
-- other consumer queries against gold tables (e.g. mol_gold.molecule_profile WHERE
-- molecule_id = X) do full table scans on multi-million-row tables.
--
-- Existing migrations (020, 065, 081) added a partial set of gold indexes for the
-- mol_gold layer but missed 9 mol_gold tables, all 8 hcs_gold tables, and the 1
-- ind_gold table. This migration fills in the gap.
--
-- Index strategy:
--   1. UNIQUE INDEX on the model's unique_key/grain (PostgREST primary lookup)
--   2. INDEX on common FK join columns (molecule_id, researcher_id, ccn, etc.)
--   3. INDEX on common filter columns (state, indication, fiscal year)
--
-- All indexes use IF NOT EXISTS so this migration is idempotent.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================================
-- mol_gold (9 tables missing primary indexes)
-- ============================================================================
CREATE UNIQUE INDEX IF NOT EXISTS mol_gold_advocacy_groups_pk_idx
    ON mol_gold.advocacy_groups (group_id);

CREATE UNIQUE INDEX IF NOT EXISTS mol_gold_advocacy_sentiment_pk_idx
    ON mol_gold.advocacy_sentiment (molecule_id, source);
CREATE INDEX IF NOT EXISTS mol_gold_advocacy_sentiment_mol_idx
    ON mol_gold.advocacy_sentiment (molecule_id);

CREATE UNIQUE INDEX IF NOT EXISTS mol_gold_financial_summary_pk_idx
    ON mol_gold.financial_summary (molecule_id, cik);
CREATE INDEX IF NOT EXISTS mol_gold_financial_summary_mol_idx
    ON mol_gold.financial_summary (molecule_id);

CREATE UNIQUE INDEX IF NOT EXISTS mol_gold_kol_drug_assoc_pk_idx
    ON mol_gold.kol_drug_associations (researcher_id, molecule_id);
CREATE INDEX IF NOT EXISTS mol_gold_kol_drug_assoc_mol_idx
    ON mol_gold.kol_drug_associations (molecule_id);
CREATE INDEX IF NOT EXISTS mol_gold_kol_drug_assoc_res_idx
    ON mol_gold.kol_drug_associations (researcher_id);

CREATE UNIQUE INDEX IF NOT EXISTS mol_gold_kol_network_pk_idx
    ON mol_gold.kol_network (source_researcher_id, target_researcher_id);
CREATE INDEX IF NOT EXISTS mol_gold_kol_network_src_idx
    ON mol_gold.kol_network (source_researcher_id);
CREATE INDEX IF NOT EXISTS mol_gold_kol_network_tgt_idx
    ON mol_gold.kol_network (target_researcher_id);

CREATE UNIQUE INDEX IF NOT EXISTS mol_gold_kol_profiles_pk_idx
    ON mol_gold.kol_profiles (researcher_id);

CREATE UNIQUE INDEX IF NOT EXISTS mol_gold_lifecycle_evidence_pk_idx
    ON mol_gold.lifecycle_evidence (molecule_id, evidence_type, evidence_id);
CREATE INDEX IF NOT EXISTS mol_gold_lifecycle_evidence_mol_idx
    ON mol_gold.lifecycle_evidence (molecule_id);

CREATE UNIQUE INDEX IF NOT EXISTS mol_gold_market_summary_pk_idx
    ON mol_gold.market_summary (molecule_id);

CREATE UNIQUE INDEX IF NOT EXISTS mol_gold_regulatory_timeline_pk_idx
    ON mol_gold.regulatory_timeline (molecule_id, agency, decision_date);
CREATE INDEX IF NOT EXISTS mol_gold_regulatory_timeline_mol_idx
    ON mol_gold.regulatory_timeline (molecule_id);

-- molecule_profile is the highest-traffic gold table — make sure inchi_key + canonical_name lookups are indexed
CREATE INDEX IF NOT EXISTS mol_gold_molecule_profile_inchi_idx
    ON mol_gold.molecule_profile (inchi_key);
CREATE INDEX IF NOT EXISTS mol_gold_molecule_profile_canon_trgm_idx
    ON mol_gold.molecule_profile USING GIN (LOWER(canonical_name) gin_trgm_ops);

-- ============================================================================
-- hcs_gold (8 tables — all missing indexes)
-- ============================================================================
CREATE UNIQUE INDEX IF NOT EXISTS hcs_gold_cms_facility_360_pk_idx
    ON hcs_gold.cms_facility_360 (ccn);
CREATE INDEX IF NOT EXISTS hcs_gold_cms_facility_360_state_idx
    ON hcs_gold.cms_facility_360 (state);
CREATE INDEX IF NOT EXISTS hcs_gold_cms_facility_360_facility_name_trgm_idx
    ON hcs_gold.cms_facility_360 USING GIN (LOWER(facility_name) gin_trgm_ops);

CREATE UNIQUE INDEX IF NOT EXISTS hcs_gold_cms_provider_360_pk_idx
    ON hcs_gold.cms_provider_360 (npi);

CREATE UNIQUE INDEX IF NOT EXISTS hcs_gold_facility_master_pk_idx
    ON hcs_gold.facility_master (provider_id);
CREATE INDEX IF NOT EXISTS hcs_gold_facility_master_state_idx
    ON hcs_gold.facility_master (state);

CREATE UNIQUE INDEX IF NOT EXISTS hcs_gold_nucc_taxonomy_pk_idx
    ON hcs_gold.nucc_taxonomy (taxonomy_code);

CREATE UNIQUE INDEX IF NOT EXISTS hcs_gold_cms_market_analytics_pk_idx
    ON hcs_gold.cms_market_analytics (geo_code, geo_level);
CREATE INDEX IF NOT EXISTS hcs_gold_cms_market_analytics_geo_idx
    ON hcs_gold.cms_market_analytics (geo_code);

CREATE UNIQUE INDEX IF NOT EXISTS hcs_gold_cms_drug_market_pk_idx
    ON hcs_gold.cms_drug_market_profile (generic_name, _source_year);
CREATE INDEX IF NOT EXISTS hcs_gold_cms_drug_market_generic_idx
    ON hcs_gold.cms_drug_market_profile (generic_name);

CREATE UNIQUE INDEX IF NOT EXISTS hcs_gold_npi_prescribing_pk_idx
    ON hcs_gold.npi_prescribing (molecule_id, gnrc_name, _source_year);
CREATE INDEX IF NOT EXISTS hcs_gold_npi_prescribing_mol_idx
    ON hcs_gold.npi_prescribing (molecule_id);

CREATE UNIQUE INDEX IF NOT EXISTS hcs_gold_prescriber_payments_pk_idx
    ON hcs_gold.prescriber_payments (molecule_id, applicable_manufacturer_or_gpo_name, _source_year);
CREATE INDEX IF NOT EXISTS hcs_gold_prescriber_payments_mol_idx
    ON hcs_gold.prescriber_payments (molecule_id);

-- ============================================================================
-- ind_gold (1 table)
-- ============================================================================
CREATE UNIQUE INDEX IF NOT EXISTS ind_gold_indication_catalog_pk_idx
    ON ind_gold.indication_catalog (icd11_code);
CREATE INDEX IF NOT EXISTS ind_gold_indication_catalog_ta_idx
    ON ind_gold.indication_catalog (therapeutic_area);

COMMIT;
