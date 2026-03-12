-- SQLMesh Model: Bronze CMS Medicare Formulary
-- Normalizes raw Medicare Part D Formulary data to typed Bronze columns
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name bronze.cms_formulary,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (formulary_id, ndc))),
    grain (formulary_id, ndc)
);

SELECT
    TRIM(formulary_id)::TEXT                    AS formulary_id,
    TRIM(ndc)::TEXT                             AS ndc,
    tier_level::INTEGER                         AS tier_level,
    COALESCE(prior_authorization, FALSE)        AS prior_authorization,
    COALESCE(step_therapy, FALSE)               AS step_therapy,
    COALESCE(quantity_limit, FALSE)             AS quantity_limit,
    _loaded_at,
    _source_file,
    _source_hash
FROM raw.cms_formulary
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
