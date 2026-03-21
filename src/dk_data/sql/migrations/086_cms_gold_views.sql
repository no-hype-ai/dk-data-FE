-- Migration 086: CMS Gold Views (016-cms-puf-datasource-integration)
--
-- Gold-layer views exposing aggregated analytics for PostgREST.
-- These are placeholder shells; SQLMesh manages the actual computation.
-- Using regular views (not materialized) so SQLMesh can replace them.
-- Column names must match silver tables from 085_cms_silver_tables.sql.

BEGIN;

-- ─── Provider 360 ─────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW hcs_gold.cms_provider_360 AS
SELECT
    npi,
    entity_type,
    COALESCE(name_first || ' ' || name_last, name_org) AS name_display,
    credential,
    primary_specialty,
    practice_state,
    total_part_d_claims,
    total_part_d_cost,
    unique_drugs_prescribed,
    total_procedures,
    unique_hcpcs_billed,
    total_medicare_payments,
    total_open_payments,
    open_payments_general_count,
    open_payments_research_count,
    latest_data_year,
    updated_at AS last_refreshed
FROM hcs_silver.cms_provider_profile;

-- ─── Facility 360 ─────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW hcs_gold.cms_facility_360 AS
SELECT
    ccn,
    facility_name,
    facility_type,
    state,
    city,
    bed_count,
    ownership_type,
    overall_quality_rating,
    total_discharges,
    total_costs,
    total_revenue,
    net_income,
    is_magnet,
    latest_data_year,
    updated_at AS last_refreshed
FROM hcs_silver.cms_facility_profile;

-- ─── Drug Market Profile ──────────────────────────────────────────────────────
CREATE OR REPLACE VIEW hcs_gold.cms_drug_market_profile AS
SELECT
    ndc,
    proprietary_name AS drug_name,
    nonproprietary_name AS generic_name,
    labeler_name,
    route,
    dosage_form,
    total_part_d_spending,
    total_part_b_spending,
    total_claims,
    total_beneficiaries,
    formulary_coverage_pct,
    avg_tier_level,
    prior_auth_pct,
    latest_data_year,
    updated_at AS last_refreshed
FROM hcs_silver.cms_drug_market;

-- ─── Market Analytics (Geographic) ────────────────────────────────────────────
CREATE OR REPLACE VIEW hcs_gold.cms_market_analytics AS
SELECT
    state,
    county,
    bene_count AS total_beneficiaries,
    per_capita_costs AS per_capita_spending,
    total_actual_costs,
    top_chronic_conditions,
    latest_data_year,
    updated_at AS last_refreshed
FROM hcs_silver.cms_geographic;

-- ─── Provider Network ─────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW hcs_gold.cms_provider_network AS
SELECT
    source_npi,
    target_npi,
    relationship_type,
    strength_score,
    shared_patient_count,
    confidence_score,
    now() AS last_refreshed
FROM hcs_silver.cms_referral_edges;

COMMIT;
