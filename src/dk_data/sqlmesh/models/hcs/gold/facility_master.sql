-- SQLMesh Model: Gold Facility Master
-- Unified facility record per provider_id, resolving the best available name/location
-- across 5 sources in hcs_silver.healthcare_facilities (cms_inpatient, cms_hospital_info,
-- cms_cost_reports, acc_tvc, hrsa).
--
-- Key design decisions:
-- 1. DISTINCT ON (provider_id) picks the row with the most data (source priority order)
-- 2. source_count reflects data confidence — facilities confirmed by ≥2 sources are flagged
-- 3. Shortage score from HRSA; bed count from cost reports (most reliable of the 5 sources)
-- Part of: issue #172 H5

MODEL (
    name hcs_gold.facility_master,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (provider_id)),
        unique_values(columns := (provider_id))
    ),
    grain provider_id
);

-- Aggregate across sources: best name, location, and available metrics per facility
WITH source_agg AS (
    SELECT
        provider_id,
        COUNT(DISTINCT source)                          AS source_count,
        -- Best name: cms_hospital_info > cms_cost_reports > cms_inpatient > acc_tvc
        MAX(CASE WHEN source = 'cms_hospital_info'  THEN facility_name END) AS name_hospital,
        MAX(CASE WHEN source = 'cms_cost_reports'   THEN facility_name END) AS name_cost_reports,
        MAX(CASE WHEN source = 'cms_inpatient'      THEN facility_name END) AS name_inpatient,
        MAX(CASE WHEN source = 'acc_tvc'            THEN facility_name END) AS name_acc,
        -- Location (prefer hospital_info, fall back to others)
        MAX(CASE WHEN source = 'cms_hospital_info'  THEN city END)          AS city_hospital,
        MAX(CASE WHEN source = 'cms_cost_reports'   THEN city END)          AS city_cost,
        MAX(CASE WHEN source = 'cms_inpatient'      THEN city END)          AS city_inpatient,
        MAX(CASE WHEN source = 'cms_hospital_info'  THEN state END)         AS state_hospital,
        MAX(CASE WHEN source = 'cms_cost_reports'   THEN state END)         AS state_cost,
        MAX(CASE WHEN source = 'cms_inpatient'      THEN state END)         AS state_inpatient,
        -- Facility type from hospital_info (most specific)
        MAX(CASE WHEN source = 'cms_hospital_info'  THEN facility_type END) AS facility_type,
        MAX(CASE WHEN source = 'acc_tvc'            THEN facility_type END) AS certification_type,
        -- Quantitative metrics from most authoritative source
        MAX(CASE WHEN source = 'cms_cost_reports'   THEN bed_count END)     AS bed_count,
        SUM(CASE WHEN source = 'cms_inpatient'      THEN total_discharges ELSE 0 END) AS total_discharges,
        MAX(CASE WHEN source = 'cms_cost_reports'   THEN avg_charges END)   AS avg_charges,
        -- HRSA shortage score
        MAX(CASE WHEN source = 'hrsa'               THEN shortage_score END) AS hrsa_shortage_score,
        -- Certifications from ACC/TVC
        MAX(CASE WHEN source = 'acc_tvc'            THEN certifications END) AS acc_certifications,
        MAX(source_updated_at)                          AS last_seen_at
    FROM hcs_silver.healthcare_facilities
    GROUP BY provider_id
)

SELECT
    gen_random_uuid()                                   AS id,
    sa.provider_id,

    -- Canonical facility name (source priority)
    COALESCE(
        sa.name_hospital,
        sa.name_cost_reports,
        sa.name_inpatient,
        sa.name_acc
    )                                                   AS facility_name,

    -- Canonical location
    COALESCE(sa.city_hospital, sa.city_cost, sa.city_inpatient)     AS city,
    COALESCE(sa.state_hospital, sa.state_cost, sa.state_inpatient)  AS state,

    sa.facility_type,
    sa.certification_type,

    -- Quantitative
    sa.bed_count,
    sa.total_discharges,
    sa.avg_charges,
    sa.hrsa_shortage_score,
    sa.acc_certifications,

    -- Data confidence
    sa.source_count,
    sa.source_count >= 2                                AS multi_source_confirmed,

    sa.last_seen_at,
    NOW()                                               AS gold_built_at

FROM source_agg sa;
