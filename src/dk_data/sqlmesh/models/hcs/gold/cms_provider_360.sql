-- SQLMesh Model: Gold CMS Provider 360 View
-- Decision-ready provider analytics with computed intensity ratios and state-level rankings.
-- Rewritten for 019 to match hcs_silver.provider_profile column schema.
-- Part of: 019-cms-puf-platform-reconciliation
--
-- Key design decisions:
-- 1. provider_profile grain is (npi, _source_year); gold takes the most recent year per NPI
-- 2. Rankings use NULLS LAST to avoid inflating rank partitions with zero-activity providers
-- 3. Providers without practice_state are included — ranked as NULL partition

MODEL (
    name hcs_gold.cms_provider_360,
    kind FULL,
    cron '@daily',
    audits (
        not_null(columns := (npi)),
        unique_values(columns := (npi))
    ),
    grain (npi)
);

-- Take the most recent year of data per NPI
WITH latest_profile AS (
    SELECT DISTINCT ON (npi) *
    FROM hcs_silver.provider_profile
    ORDER BY npi, _source_year DESC
)

SELECT
    p.npi,
    p.provider_entity_type                                                      AS entity_type,
    p.canonical_name,
    p.specialty,
    p.state                                                                     AS practice_state,
    p.city                                                                      AS practice_city,
    p.zip_code                                                                  AS practice_zip,
    p.taxonomy_code_1,
    p.taxonomy_code_2,
    p.medicare_participation_indicator,
    p.is_deactivated,

    -- Medicare utilization (Physician PUF)
    p.total_services                                                            AS total_procedures,
    p.total_unique_benes                                                        AS total_beneficiaries,
    p.total_submitted_chrg_amt,
    p.total_medicare_payment_amt                                                AS total_payment_received,
    p.total_medicare_allowed_amt,
    p.number_of_hcpcs,

    -- DME billing
    p.dme_total_chrg_amt,
    p.dme_total_payment_amt,
    p.dme_hcpcs_count,

    -- Mental health services
    p.mh_total_services,
    p.mh_total_benes,
    p.mh_total_payment_amt,

    -- Telehealth delivery
    p.telehealth_services,
    p.telehealth_benes,
    p.total_telehealth_payment,

    -- Referral network
    p.referral_partner_count,
    p.referral_total_srvcs,
    p.referral_total_benes,
    p.referral_total_alowd_amt,
    p.referral_total_pymt_amt,

    -- Ordering activity
    p.ordering_partner_count,
    p.ordering_total_srvcs,
    p.ordering_total_benes,
    p.ordering_total_alowd_amt,
    p.ordering_total_pymt_amt,

    -- Computed intensity metrics (NULL when denominator is zero)
    CASE
        WHEN p.total_unique_benes > 0
        THEN ROUND(p.total_services::NUMERIC / p.total_unique_benes, 2)
        ELSE NULL
    END                                                                         AS procedures_per_beneficiary,

    CASE
        WHEN p.total_unique_benes > 0
        THEN ROUND(p.total_medicare_payment_amt / p.total_unique_benes, 2)
        ELSE NULL
    END                                                                         AS payment_per_beneficiary,

    -- State-level rankings (NULLS LAST prevents zero-activity providers from inflating ranks)
    RANK() OVER (
        PARTITION BY p.state
        ORDER BY p.total_services DESC NULLS LAST
    )                                                                           AS state_rank_procedures,

    RANK() OVER (
        PARTITION BY p.state
        ORDER BY p.total_medicare_payment_amt DESC NULLS LAST
    )                                                                           AS state_rank_payments,

    RANK() OVER (
        PARTITION BY p.state
        ORDER BY p.total_unique_benes DESC NULLS LAST
    )                                                                           AS state_rank_beneficiaries,

    -- Specialty-level rankings within state
    RANK() OVER (
        PARTITION BY p.state, p.specialty
        ORDER BY p.total_services DESC NULLS LAST
    )                                                                           AS specialty_state_rank_procedures,

    p._source_year,
    p.created_at                                                                AS profile_built_at,
    NOW()                                                                       AS gold_built_at

FROM latest_profile p;
