-- SQLMesh Model: Silver HCS Geographic Health Metrics
-- County/state-level Medicare health and utilization metrics.
-- Grain: (geo_code, geo_level, _source_year)
--
-- Consolidates: geographic variation, chronic conditions, opioid, dual-eligible, enrollment
-- Feature: 019-cms-puf-platform-reconciliation
--
-- Column name policy: raw CMS field names preserved throughout.
--   cms_chronic_conditions: bene_cond (was chronic_condition), prvlnc (was prevalence)
--   cms_enrollment_puf: state_cd/county_cd/tot_benes/dsbl_benes (was fips/total_beneficiaries)

MODEL (
    name hcs_silver.geographic_health,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (geo_code, geo_level, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (geo_code, geo_level, _source_year))
    ),
    grain (geo_code, geo_level, _source_year)
);

WITH geo_variation AS (
    SELECT
        bene_geo_cd                         AS geo_code,
        bene_geo_lvl                        AS geo_level,
        bene_geo_desc                       AS geo_name,
        _source_year,
        tot_mdcr_stdzd_pymt_pc              AS stdz_payment_per_capita,
        tot_mdcr_pymt_pc                    AS payment_per_capita,
        tot_mdcr_stdzd_pymt_pct_chg        AS payment_pct_change,
        hosp_readmsn_rate,
        er_visits_per_1000_benes
    FROM hcs_bronze.cms_geographic_variation
    WHERE bene_geo_cd IS NOT NULL
),

-- Chronic condition prevalence (aggregated across age groups to geography level)
-- Uses raw CMS field names: bene_cond (Bene_Cond), prvlnc (Prvlnc)
chronic_agg AS (
    SELECT
        bene_geo_cd                         AS geo_code,
        _source_year,
        COUNT(DISTINCT bene_cond)           AS distinct_conditions_tracked,
        -- Top chronic conditions by prevalence (prvlnc = Prvlnc in raw CMS data)
        MAX(CASE WHEN LOWER(bene_cond) LIKE '%diabetes%' THEN prvlnc END)       AS diabetes_prevalence,
        MAX(CASE WHEN LOWER(bene_cond) LIKE '%heart failure%' THEN prvlnc END)  AS heart_failure_prevalence,
        MAX(CASE WHEN LOWER(bene_cond) LIKE '%hypertension%' THEN prvlnc END)   AS hypertension_prevalence,
        MAX(CASE WHEN LOWER(bene_cond) LIKE '%copd%' THEN prvlnc END)           AS copd_prevalence,
        MAX(CASE WHEN LOWER(bene_cond) LIKE '%depression%' THEN prvlnc END)     AS depression_prevalence,
        MAX(CASE WHEN LOWER(bene_cond) LIKE '%cancer%' THEN prvlnc END)         AS cancer_prevalence,
        AVG(prvlnc)                         AS avg_condition_prevalence,
        -- tot_mdcr_pymt_pc is per-capita payment; use as proxy for condition payment burden
        AVG(tot_mdcr_pymt_pc)              AS chronic_avg_mdcr_pymt_pc
    FROM hcs_bronze.cms_chronic_conditions
    WHERE bene_geo_cd IS NOT NULL
    GROUP BY bene_geo_cd, _source_year
),

-- Opioid prescribing (state-level via prescriber FIPS — aggregated to state grain)
-- cms_opioid_puf is prescriber-drug level; aggregate to state FIPS for geo join.
opioid AS (
    SELECT
        prscrbr_state_fips                          AS geo_code,
        _source_year,
        -- Opioid rate proxy: opioid claims as share of total claims
        CASE
            WHEN SUM(tot_clms) > 0
            THEN SUM(opioid_clms)::NUMERIC / SUM(tot_clms)
            ELSE NULL
        END                                         AS opioid_prescribing_rate,
        SUM(opioid_clms)                            AS opioid_prescriptions,
        SUM(tot_clms)                               AS total_prescriptions,
        NULL::INTEGER                               AS population  -- not available at prescriber-drug level
    FROM hcs_bronze.cms_opioid_puf
    WHERE prscrbr_state_fips IS NOT NULL
    GROUP BY prscrbr_state_fips, _source_year
),

-- Enrollment (state/county-level using state_cd and county_cd)
-- Uses raw CMS field names: state_cd, county_cd, tot_benes, dsbl_benes, esrd_benes
enrollment AS (
    SELECT
        COALESCE(county_cd, state_cd)       AS geo_code,
        _source_year,
        SUM(tot_benes)                      AS tot_benes,
        SUM(orgnl_mdcr_benes)               AS orgnl_mdcr_benes,
        SUM(ma_benes)                       AS ma_benes,
        SUM(esrd_benes)                     AS esrd_benes,
        SUM(dsbl_benes)                     AS dsbl_benes
    FROM hcs_bronze.cms_enrollment_puf
    WHERE state_cd IS NOT NULL
    GROUP BY COALESCE(county_cd, state_cd), _source_year
),

-- All geo codes
all_geos AS (
    SELECT geo_code, geo_level, _source_year FROM geo_variation
    UNION
    -- Opioid data is aggregated to state FIPS (2-digit); treat as state
    SELECT geo_code, 'State' AS geo_level, _source_year FROM opioid
    UNION
    SELECT geo_code, 'County' AS geo_level, _source_year FROM enrollment
)

SELECT
    gen_random_uuid()                   AS id,
    a.geo_code,
    a.geo_level,
    a._source_year,
    gv.geo_name,
    -- Medicare spending
    gv.stdz_payment_per_capita,
    gv.payment_per_capita,
    gv.payment_pct_change,
    gv.hosp_readmsn_rate,
    gv.er_visits_per_1000_benes,
    -- Chronic disease burden
    c.distinct_conditions_tracked,
    c.diabetes_prevalence,
    c.heart_failure_prevalence,
    c.hypertension_prevalence,
    c.copd_prevalence,
    c.depression_prevalence,
    c.cancer_prevalence,
    c.avg_condition_prevalence,
    c.chronic_avg_mdcr_pymt_pc,
    -- Opioid burden
    o.opioid_prescribing_rate,
    o.opioid_prescriptions,
    o.total_prescriptions,
    o.population,
    -- Enrollment (raw CMS field names: tot_benes, dsbl_benes, esrd_benes)
    e.tot_benes,
    e.orgnl_mdcr_benes,
    e.ma_benes,
    e.esrd_benes,
    e.dsbl_benes,
    -- Derived composite health burden score (higher = more burden)
    CASE
        WHEN gv.hosp_readmsn_rate IS NOT NULL
         AND c.avg_condition_prevalence IS NOT NULL
         AND o.opioid_prescribing_rate IS NOT NULL
        THEN (
            (gv.hosp_readmsn_rate / 0.20)           -- normalized readmission rate
            + (c.avg_condition_prevalence / 0.50)   -- normalized condition burden
            + (o.opioid_prescribing_rate / 0.30)    -- normalized opioid rate
        ) / 3.0
        ELSE NULL
    END AS health_burden_index,
    NOW()                               AS created_at,
    NOW()                               AS updated_at
FROM all_geos a
LEFT JOIN geo_variation gv ON a.geo_code = gv.geo_code AND a.geo_level = gv.geo_level AND a._source_year = gv._source_year
LEFT JOIN chronic_agg c    ON a.geo_code = c.geo_code  AND a._source_year = c._source_year
LEFT JOIN opioid o         ON a.geo_code = o.geo_code  AND a._source_year = o._source_year
LEFT JOIN enrollment e     ON a.geo_code = e.geo_code  AND a._source_year = e._source_year;
