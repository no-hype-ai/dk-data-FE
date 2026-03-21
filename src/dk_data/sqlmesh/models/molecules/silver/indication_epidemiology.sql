-- SQLMesh Model: Silver Indication Epidemiology
-- Joins WHO GHO bronze data with ICD-10 indicator mapping + CT.gov trial counts
-- Part of: 003-molecule-assessment-dashboard

MODEL (
    name mol_silver.indication_epidemiology,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (icd10_code, country_code, data_year, source)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (icd10_code, data_year, source))
    ),
    grain (icd10_code, country_code, data_year, source)
);

-- WHO GHO epidemiology data joined via indicator mapping
SELECT
    gen_random_uuid() AS id,
    m.icd10_code,
    g.indication_query AS indication_name,
    g.spatial_dim AS country_code,
    g.time_dim AS data_year,

    -- Map metric_type to appropriate columns
    CASE WHEN m.metric_type = 'incidence_rate' THEN g.numeric_value END AS incidence_rate,
    NULL::INTEGER AS incidence_count,
    CASE WHEN m.metric_type = 'prevalence_rate' THEN g.numeric_value END AS prevalence_rate,
    NULL::INTEGER AS prevalence_count,
    CASE WHEN m.metric_type = 'mortality_rate' THEN g.numeric_value END AS mortality_rate,
    CASE WHEN m.metric_type = 'mortality_count' THEN g.numeric_value::INTEGER END AS mortality_count,
    NULL::DECIMAL(5,2) AS five_year_survival,
    NULL::INTEGER AS median_age_diagnosis,
    NULL::INTEGER AS trial_count,
    NULL::INTEGER AS trial_enrollment_total,

    'who_gho' AS source,
    g.source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at

FROM mol_bronze.who_gho g
JOIN mol_silver.icd10_indicator_mapping m
    ON g.indicator_code = m.who_indicator
WHERE g.processed_to_silver = FALSE
  AND g.spatial_dim IS NOT NULL
  AND g.time_dim IS NOT NULL;
