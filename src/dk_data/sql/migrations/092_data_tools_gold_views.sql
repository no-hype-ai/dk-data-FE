-- Migration 092: Gold views for data-tools gateway sources
--
-- Creates gold-layer views for CMS sources that are NOT covered by the
-- 4 composite gold views (cms_provider_360, cms_facility_360,
-- cms_drug_market_profile, cms_market_analytics).
--
-- These thin views expose raw table data for local-first lookups
-- by the /api/v1/data-tools/{source}/query endpoint.
--
-- Sources already covered by composites (no new view needed):
--   npi-keyed  → hcs_gold.cms_provider_360
--   ccn-keyed  → hcs_gold.cms_facility_360
--   ndc-keyed  → hcs_gold.cms_drug_market_profile
--   state-keyed → hcs_gold.cms_market_analytics

BEGIN;

-- ─── Part D Spending (keyed by drug_name, not ndc) ──────────────────────────
CREATE OR REPLACE VIEW hcs_gold.cms_part_d_spending AS
SELECT
    brand_name AS drug_name,
    generic_name,
    SUM(total_spending)     AS total_spending,
    SUM(total_claims)       AS total_claims,
    SUM(total_beneficiaries) AS total_beneficiaries,
    AVG(avg_cost_per_claim) AS avg_cost_per_claim,
    MAX(year)               AS latest_year,
    MAX(_loaded_at)         AS last_refreshed
FROM hcs_raw.cms_part_d_spending
GROUP BY brand_name, generic_name;

-- ─── Part B Spending (keyed by hcpcs_code) ──────────────────────────────────
CREATE OR REPLACE VIEW hcs_gold.cms_part_b_spending AS
SELECT
    hcpcs_code,
    hcpcs_description,
    SUM(total_spending)     AS total_spending,
    SUM(total_claims)       AS total_claims,
    SUM(total_beneficiaries) AS total_beneficiaries,
    AVG(avg_cost_per_claim) AS avg_cost_per_claim,
    MAX(year)               AS latest_year,
    MAX(_loaded_at)         AS last_refreshed
FROM hcs_raw.cms_part_b_spending
GROUP BY hcpcs_code, hcpcs_description;

-- ─── CHOW (keyed by ccn, but ownership-change-specific) ────────────────────
CREATE OR REPLACE VIEW hcs_gold.cms_chow AS
SELECT
    ccn,
    old_owner,
    new_owner,
    effective_date,
    _loaded_at AS last_refreshed
FROM hcs_raw.cms_chow;

-- ─── Hospital Affiliation (keyed by ccn) ────────────────────────────────────
CREATE OR REPLACE VIEW hcs_gold.cms_hospital_affiliation AS
SELECT
    ccn,
    npi,
    affiliation_type,
    _loaded_at AS last_refreshed
FROM hcs_raw.cms_hospital_affiliation;

-- ─── RBCS Classification (keyed by hcpcs_code) ─────────────────────────────
CREATE OR REPLACE VIEW hcs_gold.cms_rbcs AS
SELECT
    hcpcs_code,
    rbcs_id,
    rbcs_category,
    rbcs_subcategory,
    rbcs_family,
    _loaded_at AS last_refreshed
FROM hcs_raw.cms_rbcs;

-- ─── NUCC Taxonomy (keyed by hcpcs_code in tool, but taxonomy_code in raw) ─
-- The tool queries by hcpcs_code but NUCC is actually keyed by taxonomy_code.
-- Expose taxonomy_code as the primary key; tool_registry should be updated.
CREATE OR REPLACE VIEW hcs_gold.cms_nucc AS
SELECT
    taxonomy_code AS hcpcs_code,  -- alias for tool compatibility
    taxonomy_code,
    provider_type,
    classification,
    specialization,
    grouping_name,
    _loaded_at AS last_refreshed
FROM hcs_raw.cms_nucc;

-- ─── USP Drug Classification (keyed by drug_name) ──────────────────────────
CREATE OR REPLACE VIEW hcs_gold.cms_usp AS
SELECT
    drug_name,
    ndc,
    usp_category,
    usp_class,
    _loaded_at AS last_refreshed
FROM hcs_raw.cms_usp;

-- ─── Stabilis IV Compatibility (keyed by drug_name) ────────────────────────
CREATE OR REPLACE VIEW hcs_gold.cms_stabilis AS
SELECT
    drug_name,
    route,
    diluent,
    stability_hours,
    storage_condition,
    _loaded_at AS last_refreshed
FROM hcs_raw.cms_stabilis;

-- ─── DDInter Drug Interactions (keyed by drug_name) ────────────────────────
CREATE OR REPLACE VIEW hcs_gold.cms_ddinter AS
SELECT
    drug_a AS drug_name,
    drug_b,
    interaction_level,
    description,
    _loaded_at AS last_refreshed
FROM hcs_raw.cms_ddinter;

-- ─── Formulary (keyed by ndc) ──────────────────────────────────────────────
CREATE OR REPLACE VIEW hcs_gold.cms_formulary AS
SELECT
    ndc,
    formulary_id,
    tier_level,
    prior_authorization,
    step_therapy,
    quantity_limit,
    _loaded_at AS last_refreshed
FROM hcs_raw.cms_formulary;

-- ─── NDC Directory (keyed by ndc) ──────────────────────────────────────────
-- Separate from drug_market_profile which aggregates spending data.
CREATE OR REPLACE VIEW hcs_gold.cms_ndc AS
SELECT
    ndc,
    proprietary_name,
    nonproprietary_name,
    labeler_name,
    dosage_form,
    route,
    product_type,
    _loaded_at AS last_refreshed
FROM hcs_raw.cms_ndc;

-- ─── DMEPOS (keyed by npi) ─────────────────────────────────────────────────
CREATE OR REPLACE VIEW hcs_gold.cms_dmepos AS
SELECT
    npi,
    hcpcs_code,
    SUM(total_services)      AS total_services,
    SUM(total_beneficiaries) AS total_beneficiaries,
    AVG(avg_submitted_charge) AS avg_submitted_charge,
    AVG(avg_medicare_payment) AS avg_medicare_payment,
    MAX(year)                AS latest_year,
    MAX(_loaded_at)          AS last_refreshed
FROM hcs_raw.cms_dmepos
GROUP BY npi, hcpcs_code;

-- ─── Post-Acute Care (keyed by ccn/provider_id) ────────────────────────────
CREATE OR REPLACE VIEW hcs_gold.cms_post_acute AS
SELECT
    provider_id AS ccn,
    provider_type,
    SUM(total_episodes)          AS total_episodes,
    AVG(avg_spending_per_episode) AS avg_spending_per_episode,
    MAX(year)                    AS latest_year,
    MAX(_loaded_at)              AS last_refreshed
FROM hcs_raw.cms_post_acute
GROUP BY provider_id, provider_type;

-- ─── NPPES (keyed by npi) — direct view for bulk-only local lookup ─────────
CREATE OR REPLACE VIEW hcs_gold.cms_nppes AS
SELECT
    npi,
    entity_type,
    name_first,
    name_last,
    name_org,
    credential,
    taxonomy_code,
    practice_state,
    practice_city,
    practice_zip,
    _loaded_at AS last_refreshed
FROM hcs_raw.cms_nppes;

-- ─── POS (keyed by ccn) — direct view for bulk-only local lookup ───────────
CREATE OR REPLACE VIEW hcs_gold.cms_pos AS
SELECT
    ccn,
    facility_name,
    facility_type,
    state,
    city,
    bed_count,
    _loaded_at AS last_refreshed
FROM hcs_raw.cms_pos;

-- ─── HCRIS (keyed by ccn) — direct view for bulk-only local lookup ────────
CREATE OR REPLACE VIEW hcs_gold.cms_hcris AS
SELECT
    provider_ccn AS ccn,
    fiscal_year_begin,
    fiscal_year_end,
    total_costs,
    total_revenue,
    net_income,
    _loaded_at AS last_refreshed
FROM hcs_raw.cms_hcris;

-- ─── Magnet (keyed by ccn) — direct view for bulk-only local lookup ───────
CREATE OR REPLACE VIEW hcs_gold.cms_magnet AS
SELECT
    facility_id AS ccn,
    facility_name,
    city,
    state,
    designation_date,
    expiration_date,
    _loaded_at AS last_refreshed
FROM hcs_raw.cms_magnet;

COMMIT;
