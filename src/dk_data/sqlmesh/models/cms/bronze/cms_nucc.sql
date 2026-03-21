-- SQLMesh Model: Bronze CMS NUCC Taxonomy
-- Normalizes raw National Uniform Claim Committee Taxonomy to typed Bronze columns
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_nucc,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (taxonomy_code))),
    grain (taxonomy_code)
);

SELECT
    TRIM(taxonomy_code)::TEXT                   AS taxonomy_code,
    UPPER(TRIM(provider_type))                  AS provider_type,
    UPPER(TRIM(classification))                 AS classification,
    UPPER(TRIM(specialization))                 AS specialization,
    UPPER(TRIM(grouping_name))                  AS grouping_name,
    _loaded_at,
    _source_file,
    _source_hash
FROM hcs_raw.cms_nucc
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
