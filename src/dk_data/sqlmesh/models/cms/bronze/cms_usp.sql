-- SQLMesh Model: Bronze CMS USP Drug Classification
-- Normalizes raw US Pharmacopeia Drug Classifications to typed Bronze columns
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name bronze.cms_usp,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (usp_category, usp_class))),
    grain (usp_category, usp_class)
);

SELECT
    UPPER(TRIM(usp_category))                   AS usp_category,
    UPPER(TRIM(usp_class))                      AS usp_class,
    UPPER(TRIM(drug_name))                      AS drug_name,
    TRIM(ndc)::TEXT                             AS ndc,
    _loaded_at,
    _source_file,
    _source_hash
FROM raw.cms_usp
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
