-- SQLMesh Model: Silver Indication Epidemiology
-- Joins WHO GHO bronze data with ICD-10 indicator mapping + ontology enrichment.
-- Part of: 003-molecule-assessment-dashboard
--
-- Indicator coverage: ~300 WHO GHO indicators via mol_silver.icd10_indicator_mapping.
-- Ontology enrichment: therapeutic_area, indication_name from ind_silver.indication_ontology.

MODEL (
    name ind_silver.epidemiology,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (icd10_code, spatial_dim, time_dim, source)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (icd10_code, time_dim, source))
    ),
    grain (icd10_code, spatial_dim, time_dim, source)
);

-- WHO GHO epidemiology data joined via indicator mapping
SELECT
    gen_random_uuid()                                                       AS id,
    m.icd10_code,
    -- Ontology enrichment (therapeutic area + canonical indication name)
    o.therapeutic_area,
    o.indication_name,
    m.indication_label                                                      AS indicator_label,
    g.indication_query,
    g.spatial_dim,
    g.time_dim,

    -- Map metric_type to appropriate columns
    CASE WHEN m.metric_type = 'incidence_rate'  THEN g.numeric_value END   AS incidence_rate,
    NULL::INTEGER                                                           AS incidence_count,
    CASE WHEN m.metric_type = 'prevalence_rate' THEN g.numeric_value END   AS prevalence_rate,
    NULL::INTEGER                                                           AS prevalence_count,
    CASE WHEN m.metric_type = 'mortality_rate'  THEN g.numeric_value END   AS mortality_rate,
    CASE WHEN m.metric_type = 'mortality_count' THEN g.numeric_value::INTEGER END AS mortality_count,
    NULL::DECIMAL(5,2)                                                      AS five_year_survival,
    NULL::INTEGER                                                           AS median_age_diagnosis,
    NULL::INTEGER                                                           AS trial_count,
    NULL::INTEGER                                                           AS trial_enrollment_total,

    -- Bronze columns carried forward (zero data loss)
    g.indicator_code,
    g.numeric_value,
    g.dim1,
    g.low,
    g.high,
    m.metric_type,

    g.id                                                                    AS bronze_id,
    'who_gho'                                                               AS source,
    g.source_updated_at,
    NOW()                                                                   AS created_at,
    NOW()                                                                   AS updated_at

FROM mol_bronze.who_gho g
JOIN mol_silver.icd10_indicator_mapping m
    ON g.indicator_code = m.who_indicator
LEFT JOIN ind_silver.indication_ontology o
    ON o.icd10_code = m.icd10_code
WHERE g.processed_to_silver = FALSE
  AND g.spatial_dim IS NOT NULL
  AND g.time_dim IS NOT NULL;
