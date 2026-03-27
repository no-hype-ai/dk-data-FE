-- SQLMesh Model: Gold CMS Facility 360 View
-- Decision-ready facility analytics with bed utilization estimates,
-- state-level market share, and quality tier classification
-- Part of: 016-cms-puf-datasource-integration (Phase 3 — Facility MVP)

MODEL (
    name hcs_gold.cms_facility_360,
    kind FULL,
    cron '@daily',
    audits (
        not_null(columns := (ccn)),
        unique_values(columns := (ccn))
    ),
    grain (ccn)
);

WITH state_totals AS (
    SELECT
        state,
        SUM(total_discharges)                   AS state_total_discharges,
        SUM(total_outpatient_services)          AS state_total_outpatient_services,
        SUM(total_beds)                         AS state_total_beds
    FROM hcs_silver.cms_facility_profile
    WHERE state IS NOT NULL
    GROUP BY state
)

SELECT
    f.ccn,
    f.facility_name,
    f.facility_type,
    f.address,
    f.city,
    f.state,
    f.zip_code,

    -- Capacity
    f.total_beds,
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

    -- Bed utilization estimate (discharges per bed per year)
    CASE
        WHEN f.total_beds > 0
        THEN ROUND(f.total_discharges::NUMERIC / f.total_beds, 2)
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
            f.total_beds::NUMERIC / st.state_total_beds * 100, 4
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
        ORDER BY f.total_beds DESC
    )                                                                           AS state_rank_beds,

    RANK() OVER (
        PARTITION BY f.state
        ORDER BY f.total_revenue DESC NULLS LAST
    )                                                                           AS state_rank_revenue,

    f.profile_built_at,
    NOW()                                                                       AS gold_built_at

FROM hcs_silver.cms_facility_profile f
LEFT JOIN state_totals st ON f.state = st.state
WHERE f.state IS NOT NULL;
