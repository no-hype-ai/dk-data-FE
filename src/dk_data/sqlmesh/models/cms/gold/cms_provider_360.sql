-- SQLMesh Model: Gold CMS Provider 360 View
-- Decision-ready provider analytics with computed ratios and state-level rankings
-- Part of: 016-cms-puf-datasource-integration
--
-- Key design decisions:
-- 1. Providers without practice_state are included (not dropped) — ranked as NULL partition
-- 2. Rankings use NULLS LAST to avoid inflating rank partitions with zero-activity providers
-- 3. Column rename: total_beneficiaries → total_beneficiaries to reflect silver change

MODEL (
    name gold.cms_provider_360,
    kind FULL,
    cron '@daily',
    audits (
        not_null(columns := (npi)),
        unique_values(columns := (npi))
    ),
    grain (npi)
);

SELECT
    p.npi,
    p.entity_type,
    p.name_first,
    p.name_last,
    p.name_org,
    p.credential,
    p.primary_specialty,
    p.specialty_classification,
    p.specialty_detail,
    p.practice_state,
    p.practice_city,
    p.practice_zip,
    p.gender,
    p.enumeration_date,

    -- Volume metrics
    p.total_prescriptions,
    p.total_drug_cost,
    p.distinct_drugs_prescribed,
    p.total_procedures,
    p.total_beneficiaries,
    p.total_payment_received,
    p.distinct_payers,
    p.total_payment_records,

    -- Computed intensity metrics (NULL when denominator is zero, not division by zero)
    CASE
        WHEN p.total_beneficiaries > 0
        THEN ROUND(p.total_prescriptions::NUMERIC / p.total_beneficiaries, 2)
        ELSE NULL
    END                                                                 AS prescribing_intensity,

    CASE
        WHEN p.total_prescriptions > 0
        THEN ROUND(p.total_drug_cost / p.total_prescriptions, 2)
        ELSE NULL
    END                                                                 AS cost_per_claim,

    CASE
        WHEN p.total_beneficiaries > 0
        THEN ROUND(p.total_procedures::NUMERIC / p.total_beneficiaries, 2)
        ELSE NULL
    END                                                                 AS procedures_per_beneficiary,

    CASE
        WHEN p.total_beneficiaries > 0
        THEN ROUND(p.total_payment_received / p.total_beneficiaries, 2)
        ELSE NULL
    END                                                                 AS payment_per_beneficiary,

    -- State-level rankings (NULLS LAST prevents zero-activity providers from inflating ranks)
    RANK() OVER (
        PARTITION BY p.practice_state
        ORDER BY p.total_prescriptions DESC NULLS LAST
    )                                                                   AS state_rank_prescriptions,

    RANK() OVER (
        PARTITION BY p.practice_state
        ORDER BY p.total_drug_cost DESC NULLS LAST
    )                                                                   AS state_rank_drug_cost,

    RANK() OVER (
        PARTITION BY p.practice_state
        ORDER BY p.total_procedures DESC NULLS LAST
    )                                                                   AS state_rank_procedures,

    RANK() OVER (
        PARTITION BY p.practice_state
        ORDER BY p.total_payment_received DESC NULLS LAST
    )                                                                   AS state_rank_payments,

    -- Specialty-level rankings within state
    RANK() OVER (
        PARTITION BY p.practice_state, p.primary_specialty
        ORDER BY p.total_prescriptions DESC NULLS LAST
    )                                                                   AS specialty_state_rank_prescriptions,

    p.profile_built_at,
    NOW()                                                               AS gold_built_at

FROM silver.cms_provider_profile p;
