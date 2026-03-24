-- SQLMesh Model: Bronze CMS Chronic Conditions PUF
-- Extracts typed columns from JSONB response_body
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_chronic_conditions,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (state, condition))),
    grain (state, condition)
);

SELECT
    response_body->>'state'                                     AS state,
    response_body->>'condition'                                 AS condition,
    (response_body->>'prevalence_rate')::NUMERIC(6,4)           AS prevalence_rate,
    (response_body->>'total_beneficiaries_with_condition')::INTEGER AS total_beneficiaries_with_condition,
    (response_body->>'per_capita_spending')::NUMERIC(12,2)      AS per_capita_spending,
    response_body                                               AS raw_json,
    id                                                          AS raw_source_id,
    'cms_chronic_conditions'                                    AS source,
    ingested_at
FROM hcs_raw.cms_chronic_conditions
WHERE response_status = 200
  AND ingested_at BETWEEN @start_dt AND @end_dt;
