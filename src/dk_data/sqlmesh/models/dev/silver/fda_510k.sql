-- SQLMesh Model: Silver FDA 510(k) Clearances
-- Entity-resolved 510(k) fact table. Each row references:
--   - device_id: resolved via dev_silver.resolve_device(p_k_number => k_number)
--   - company_id: resolved via mol_silver.resolve_company(p_name => applicant)
--     (FIRST LIVE CALLSITE of resolve_company — audit 2026-04-20 §3)
-- Per Rule P3 (bridge placement), named-parameter calls are REQUIRED; positional
-- calls miss silently because tier-1 parameters are structural identifiers the
-- source may not have.
--
-- device_id and company_id are bigint (NOT UUID).
-- Grain: k_number

MODEL (
    name dev_silver.fda_510k,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key k_number
    ),
    cron '@weekly',
    audits (
        not_null(columns := (k_number, device_id))
    ),
    grain k_number
);

SELECT
    -- Entity-resolved FKs (bigint)
    dev_silver.resolve_device(
        p_k_number => b.k_number,
        p_name     => b.device_name
    )                                                                    AS device_id,

    mol_silver.resolve_company(
        p_name => b.applicant
    )                                                                    AS company_id,

    -- Natural key
    b.k_number,

    -- Applicant (string retained for audit/fallback)
    b.applicant                                                          AS applicant_name,

    -- Dates
    b.date_received,
    b.decision_date,

    -- Regulatory decision
    b.decision_code,
    b.decision_description,
    b.clearance_type,
    (b.third_party_flag = 'Y')                                           AS is_third_party,
    (b.expedited_review_flag = 'Y')                                      AS is_expedited,

    -- Device metadata
    b.device_name,
    b.product_code,
    b.openfda_device_name,
    b.openfda_device_class,
    b.openfda_regulation_number,
    b.openfda_medical_specialty_description                              AS medical_specialty,

    -- Geography (useful when FEI is not yet wired)
    b.city,
    b.state,
    b.country_code,

    -- Advisory committee
    b.advisory_committee,
    b.advisory_committee_description,

    -- Raw tracking
    b.raw_source_id,
    b.source                                                             AS source_id,
    b.source_updated_at,
    NOW()                                                                AS silver_loaded_at

FROM dev_bronze.openfda_device_510k AS b
WHERE b.processed_to_silver = FALSE
  AND b.k_number IS NOT NULL;
