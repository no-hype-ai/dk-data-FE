-- Migration 031/043: API materialized views with gold-grade joins
-- Feature: 001-silver-medallion-rebuild / T184
--
-- Creates materialized views in api schema filtered to confidence >= 0.95.
-- Refreshed nightly by cronjob-refresh-api-views CronJob.

-- ----------------------------------------------------------------
-- api.facility_summary
-- ----------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS api.facility_summary AS
SELECT
    f.facility_id,
    f.facility_name,
    f.facility_type,
    f.address_city,
    f.address_state,
    f.address_country,
    f.npi,
    f.cms_certification_number,
    f.bed_count,
    f.star_rating,
    f.last_updated_at
FROM hcs_gold.dim_hospital f
WHERE f.confidence_score >= 0.95
  AND f.is_active = TRUE
WITH DATA;

CREATE UNIQUE INDEX IF NOT EXISTS api_facility_summary_pk
    ON api.facility_summary (facility_id);
CREATE INDEX IF NOT EXISTS api_facility_summary_state
    ON api.facility_summary (address_state);

GRANT SELECT ON api.facility_summary TO web_anon, analyst;

-- ----------------------------------------------------------------
-- api.molecule_summary
-- ----------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS api.molecule_summary AS
SELECT
    m.molecule_id,
    m.canonical_name,
    m.canonical_smiles,
    m.inchi_key,
    m.molecular_weight,
    m.drug_type,
    m.approval_status,
    m.approval_date,
    m.max_phase,
    m.indication_count,
    m.confidence_score
FROM mol_gold.molecule_profiles_agg m
WHERE m.confidence_score >= 0.95
WITH DATA;

CREATE UNIQUE INDEX IF NOT EXISTS api_molecule_summary_pk
    ON api.molecule_summary (molecule_id);
CREATE INDEX IF NOT EXISTS api_molecule_summary_inchi
    ON api.molecule_summary (inchi_key);

GRANT SELECT ON api.molecule_summary TO web_anon, analyst;

-- ----------------------------------------------------------------
-- api.trial_summary
-- ----------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS api.trial_summary AS
SELECT
    t.trial_id,
    t.nct_id,
    t.title,
    t.phase,
    t.status,
    t.start_date,
    t.completion_date,
    t.primary_outcome,
    t.sponsor_name,
    t.condition_count,
    t.intervention_count,
    t.confidence_score
FROM mol_gold.trial_analytics_agg t
WHERE t.confidence_score >= 0.95
WITH DATA;

CREATE UNIQUE INDEX IF NOT EXISTS api_trial_summary_pk
    ON api.trial_summary (trial_id);
CREATE INDEX IF NOT EXISTS api_trial_summary_nct
    ON api.trial_summary (nct_id);

GRANT SELECT ON api.trial_summary TO web_anon, analyst;
