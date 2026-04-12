-- NOTE: This gold model reads from a single silver entity hub (hcs_silver.geographic_health)
-- which itself consolidates 7+ bronze sources. The >=2 source rule is satisfied at the silver layer.
--
-- SQLMesh Model: Gold CMS Market Analytics
-- Decision-ready geographic market analytics with normalized cost and burden indices.
-- Rewritten for 019 to match hcs_silver.geographic_health column schema.
-- Part of: 019-cms-puf-platform-reconciliation
--
-- Key design decisions:
-- 1. geographic_health grain is (geo_code, geo_level, _source_year); gold takes most recent year per geo
-- 2. cost_index and chronic_burden_score normalized relative to national average at same geo_level
-- 3. health_burden_index from silver is a composite (readmission + chronic + opioid)

MODEL (
    name hcs_gold.cms_market_analytics,
    kind FULL,
    cron '@daily',
    audits (
        not_null(columns := (geo_code, geo_level))
    ),
    grain (geo_code, geo_level)
);

-- Take most recent year of data per geography
WITH latest_geo AS (
    SELECT DISTINCT ON (geo_code, geo_level) *
    FROM hcs_silver.geographic_health
    ORDER BY geo_code, geo_level, _source_year DESC
),

-- National averages at each geo_level for normalization
national_avg AS (
    SELECT
        geo_level,
        AVG(payment_per_capita)         AS avg_payment_per_capita,
        AVG(avg_condition_prevalence)   AS avg_condition_prevalence,
        AVG(hosp_readmsn_rate)          AS avg_readmission_rate,
        AVG(opioid_prescribing_rate)    AS avg_opioid_rate
    FROM latest_geo
    GROUP BY geo_level
)

SELECT
    g.geo_code,
    g.geo_level,
    g.geo_name,
    g._source_year                                                              AS data_year,
    g.tot_benes                                                                 AS total_beneficiaries,
    g.payment_per_capita,
    g.stdz_payment_per_capita,
    g.payment_pct_change,

    -- Cost index: normalized per-capita payment relative to national average at this geo_level
    CASE
        WHEN n.avg_payment_per_capita > 0
        THEN ROUND(g.payment_per_capita / n.avg_payment_per_capita, 4)
        ELSE NULL
    END                                                                         AS cost_index,

    -- Chronic disease burden
    g.avg_condition_prevalence,
    g.diabetes_prevalence,
    g.heart_failure_prevalence,
    g.hypertension_prevalence,
    g.copd_prevalence,
    g.depression_prevalence,
    g.cancer_prevalence,

    -- Chronic burden score: normalized prevalence relative to national average
    CASE
        WHEN n.avg_condition_prevalence > 0
        THEN ROUND(g.avg_condition_prevalence / n.avg_condition_prevalence, 4)
        ELSE NULL
    END                                                                         AS chronic_burden_score,

    -- Hospital quality and utilization
    g.hosp_readmsn_rate,
    g.er_visits_per_1000_benes,

    -- Readmission ratio: normalized relative to national average
    CASE
        WHEN n.avg_readmission_rate > 0
        THEN ROUND(g.hosp_readmsn_rate / n.avg_readmission_rate, 4)
        ELSE NULL
    END                                                                         AS readmission_ratio,

    -- Opioid burden
    g.opioid_prescribing_rate,
    CASE
        WHEN n.avg_opioid_rate > 0
        THEN ROUND(g.opioid_prescribing_rate / n.avg_opioid_rate, 4)
        ELSE NULL
    END                                                                         AS opioid_burden_ratio,

    -- Composite health burden (from silver)
    g.health_burden_index,

    -- Enrollment mix
    g.orgnl_mdcr_benes,
    g.ma_benes,
    g.esrd_benes,
    g.dsbl_benes,

    -- Dual eligible population
    g.dual_tot_benes,
    g.dual_full_benes,
    g.dual_partial_benes,
    g.dual_eligibility_rate,

    -- Medicare Advantage penetration
    g.ma_enrollment,
    g.ma_plan_count,
    g.ma_avg_risk_score,
    g.ma_avg_star_rating,
    g.ma_participation_rate,

    -- FFS claim-type aggregates
    g.claim_total_clms,
    g.claim_tot_benes,
    g.claim_total_mdcr_pymt,
    g.claim_avg_mdcr_pymt,

    -- Utilization intensity metrics
    g.util_srvcs_per_bene,
    g.util_ip_cvrd_stays_per_1000,
    g.util_avg_ip_los,
    g.util_er_visits_per_1000,
    g.util_phy_visits_per_bene,
    g.util_tot_mdcr_pymt_pc,

    -- State-level rankings (only meaningful within same geo_level)
    RANK() OVER (
        PARTITION BY g.geo_level
        ORDER BY g.payment_per_capita DESC NULLS LAST
    )                                                                           AS rank_cost,

    RANK() OVER (
        PARTITION BY g.geo_level
        ORDER BY g.tot_benes DESC NULLS LAST
    )                                                                           AS rank_beneficiaries,

    RANK() OVER (
        PARTITION BY g.geo_level
        ORDER BY g.health_burden_index DESC NULLS LAST
    )                                                                           AS rank_health_burden,

    g.created_at                                                                AS profile_built_at,
    NOW()                                                                       AS gold_built_at

FROM latest_geo g
JOIN national_avg n ON g.geo_level = n.geo_level;
