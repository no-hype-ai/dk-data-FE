-- SQLMesh Model: Bronze CMS Chronic Conditions
-- Normalizes raw Chronic Conditions PUF to typed Bronze columns
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name bronze.cms_chronic_conditions,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (state, condition))),
    grain (state, condition)
);

SELECT
    UPPER(TRIM(state))                                          AS state,
    UPPER(TRIM(condition))                                      AS condition,
    COALESCE(prevalence_rate, 0)::NUMERIC(6,4)                  AS prevalence_rate,
    COALESCE(total_beneficiaries_with_condition, 0)::INTEGER    AS total_beneficiaries_with_condition,
    COALESCE(per_capita_spending, 0)::NUMERIC(12,2)             AS per_capita_spending,
    _loaded_at,
    _source_file,
    _source_hash
FROM hcs_raw.cms_chronic_conditions
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
