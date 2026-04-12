-- SQLMesh Model: Gold CMS Facility 360 View
-- Decision-ready facility analytics with bed utilization estimates,
-- state-level market share, quality tier classification, and post-acute services.
-- Updated for 019-cms-puf-platform-reconciliation: adds SNF/home health/hospice
-- metrics from hcs_silver.facility_profile (new 019 silver model).
--
-- Silver sources:
--   1. hcs_silver.cms_facility_profile — POS + PECOS + quality + HCRIS + affiliation (016)
--   2. hcs_silver.facility_profile     — hospital_general_info + cost_reports +
--                                        inpatient + outpatient + SNF + home health + hospice (019)

MODEL (
    name hcs_gold.cms_facility_360,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (ccn)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (ccn)),
        unique_values(columns := (ccn))
    ),
    grain (ccn),
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

-- Most-recent year per facility from the 019 facility_profile silver
WITH fp_latest AS (
    SELECT DISTINCT ON (provider_id) *
    FROM hcs_silver.facility_profile
    ORDER BY provider_id, _source_year DESC
),

state_totals AS (
    SELECT
        state,
        SUM(total_discharges)                   AS state_total_discharges,
        SUM(total_outpatient_services)          AS state_total_outpatient_services,
        SUM(beds)                               AS state_total_beds
    FROM hcs_silver.cms_facility_profile
    WHERE state IS NOT NULL
    GROUP BY state
)

SELECT
    f.ccn,
    f.facility_name,
    f.provider_type,
    f.address,
    f.city,
    f.state,
    f.zip_code,

    -- Capacity
    f.beds,
    f.ownership_type,
    f.hospital_type,

    -- Quality
    f.overall_quality_rating,
    CASE
        WHEN f.overall_quality_rating >= 4 THEN 'High'
        WHEN f.overall_quality_rating >= 3 THEN 'Medium'
        WHEN f.overall_quality_rating >= 1 THEN 'Low'
        ELSE 'Unrated'
    END                                                                         AS quality_tier,

    -- Volume metrics
    f.total_discharges,
    f.distinct_drg_count,
    f.weighted_avg_medicare_payment,
    f.total_outpatient_services,
    f.distinct_apc_count,
    f.affiliated_provider_count,

    -- Enrollment & designations
    f.enrollment_status,
    f.magnet_status,
    f.magnet_designation_date,

    -- Financial metrics
    f.total_costs,
    f.total_revenue,
    f.net_income,

    -- SNF metrics (from 019 facility_profile)
    fp2.snf_total_benes,
    fp2.snf_total_cvrd_days,
    fp2.snf_avg_cvrd_days,
    fp2.snf_total_alowd_amt,
    fp2.snf_medicare_payment,
    fp2.snf_avg_payment,
    fp2.snf_rug_count,

    -- Home health metrics (from 019 facility_profile)
    fp2.hh_total_episodes,
    fp2.hh_total_benes,
    fp2.hh_avg_medicare_payment,
    fp2.hh_avg_dual_pct,

    -- Hospice metrics (from 019 facility_profile)
    fp2.hospice_total_benes,
    fp2.hospice_total_payment,
    fp2.hospice_avg_payment,
    fp2.hospice_service_count,

    -- Post-acute care classification
    CASE
        WHEN fp2.snf_total_benes    IS NOT NULL THEN TRUE ELSE FALSE END        AS has_snf_services,
    CASE
        WHEN fp2.hh_total_benes     IS NOT NULL THEN TRUE ELSE FALSE END        AS has_home_health,
    CASE
        WHEN fp2.hospice_total_benes IS NOT NULL THEN TRUE ELSE FALSE END       AS has_hospice,

    -- Bed utilization estimate (discharges per bed per year)
    CASE
        WHEN f.beds > 0
        THEN ROUND(f.total_discharges::NUMERIC / f.beds, 2)
        ELSE NULL
    END                                                                         AS bed_utilization_ratio,

    -- Market share within state (by discharges)
    CASE
        WHEN st.state_total_discharges > 0
        THEN ROUND(
            f.total_discharges::NUMERIC / st.state_total_discharges * 100, 4
        )
        ELSE NULL
    END                                                                         AS state_discharge_market_share_pct,

    -- Market share within state (by outpatient services)
    CASE
        WHEN st.state_total_outpatient_services > 0
        THEN ROUND(
            f.total_outpatient_services::NUMERIC / st.state_total_outpatient_services * 100, 4
        )
        ELSE NULL
    END                                                                         AS state_outpatient_market_share_pct,

    -- Market share within state (by beds)
    CASE
        WHEN st.state_total_beds > 0
        THEN ROUND(
            f.beds::NUMERIC / st.state_total_beds * 100, 4
        )
        ELSE NULL
    END                                                                         AS state_bed_market_share_pct,

    -- State-level rankings
    RANK() OVER (
        PARTITION BY f.state
        ORDER BY f.total_discharges DESC
    )                                                                           AS state_rank_discharges,

    RANK() OVER (
        PARTITION BY f.state
        ORDER BY f.total_outpatient_services DESC
    )                                                                           AS state_rank_outpatient,

    RANK() OVER (
        PARTITION BY f.state
        ORDER BY f.beds DESC
    )                                                                           AS state_rank_beds,

    RANK() OVER (
        PARTITION BY f.state
        ORDER BY f.total_revenue DESC NULLS LAST
    )                                                                           AS state_rank_revenue,

    f.profile_built_at,
    NOW()                                                                       AS gold_built_at

FROM hcs_silver.cms_facility_profile f
LEFT JOIN fp_latest fp2 ON f.ccn = fp2.provider_id
LEFT JOIN state_totals st ON f.state = st.state
WHERE f.state IS NOT NULL;
