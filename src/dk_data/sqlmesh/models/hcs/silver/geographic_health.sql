-- SQLMesh Model: Silver HCS Geographic Health Metrics
-- County/state-level Medicare health and utilization metrics.
-- Grain: (geo_code, geo_level, _source_year)
--
-- Consolidates: geographic variation, chronic conditions, opioid, dual-eligible, enrollment
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_silver.geographic_health,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (geo_code, geo_level, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (geo_code, geo_level, _source_year)),
        unique_values(columns := (geo_code, geo_level, _source_year))
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
chronic_agg AS (
    SELECT
        bene_geo_cd                         AS geo_code,
        _source_year,
        COUNT(DISTINCT chronic_condition)   AS distinct_conditions_tracked,
        -- Top chronic conditions by prevalence
        MAX(CASE WHEN LOWER(chronic_condition) LIKE '%diabetes%' THEN prevalence END) AS diabetes_prevalence,
        MAX(CASE WHEN LOWER(chronic_condition) LIKE '%heart failure%' THEN prevalence END) AS heart_failure_prevalence,
        MAX(CASE WHEN LOWER(chronic_condition) LIKE '%hypertension%' THEN prevalence END) AS hypertension_prevalence,
        MAX(CASE WHEN LOWER(chronic_condition) LIKE '%copd%' THEN prevalence END) AS copd_prevalence,
        MAX(CASE WHEN LOWER(chronic_condition) LIKE '%depression%' THEN prevalence END) AS depression_prevalence,
        MAX(CASE WHEN LOWER(chronic_condition) LIKE '%cancer%' THEN prevalence END) AS cancer_prevalence,
        AVG(prevalence)                     AS avg_condition_prevalence,
        SUM(total_medicare_payment)         AS chronic_total_medicare_payment
    FROM hcs_bronze.cms_chronic_conditions
    WHERE bene_geo_cd IS NOT NULL
    GROUP BY bene_geo_cd, _source_year
),

-- Opioid prescribing (county-level FIPS)
opioid AS (
    SELECT
        fips                                AS geo_code,
        _source_year,
        opioid_prescribing_rate,
        opioid_prescriptions,
        total_prescriptions,
        population
    FROM hcs_bronze.cms_opioid_puf
    WHERE fips IS NOT NULL
),

-- Enrollment (county-level FIPS)
enrollment AS (
    SELECT
        fips                                AS geo_code,
        _source_year,
        total_beneficiaries,
        aged_esrd_benes,
        disabled_benes,
        esrd_benes,
        aged_benes
    FROM hcs_bronze.cms_enrollment_puf
    WHERE fips IS NOT NULL
),

-- All geo codes
all_geos AS (
    SELECT geo_code, geo_level, _source_year FROM geo_variation
    UNION
    -- Opioid and enrollment are FIPS (county-level); treat as county
    SELECT geo_code, 'County' AS geo_level, _source_year FROM opioid
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
    c.chronic_total_medicare_payment,
    -- Opioid burden
    o.opioid_prescribing_rate,
    o.opioid_prescriptions,
    o.total_prescriptions,
    o.population,
    -- Enrollment
    e.total_beneficiaries,
    e.aged_esrd_benes,
    e.disabled_benes,
    e.esrd_benes,
    e.aged_benes,
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
LEFT JOIN geo_variation gv ON a.geo_code = gv.geo_code AND a._source_year = gv._source_year
LEFT JOIN chronic_agg c    ON a.geo_code = c.geo_code  AND a._source_year = c._source_year
LEFT JOIN opioid o         ON a.geo_code = o.geo_code  AND a._source_year = o._source_year
LEFT JOIN enrollment e     ON a.geo_code = e.geo_code  AND a._source_year = e._source_year;
