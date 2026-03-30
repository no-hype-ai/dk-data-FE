-- SQLMesh Model: Bronze CMS Medicare Part D Formulary
-- Extracts typed columns from JSONB response_body
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_formulary,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (rxcui))),
    grain (formulary_id, rxcui)
);

SELECT
    response_body->>'formulary_id'      AS formulary_id,
    response_body->>'rxcui'             AS rxcui,
    response_body->>'tier_level'        AS tier_level,
    response_body->>'prior_auth'        AS prior_auth,
    response_body->>'step_therapy'      AS step_therapy,
    response_body->>'quantity_limit'    AS quantity_limit,
    response_body                       AS raw_json,
    id                                  AS raw_source_id,
    'cms_formulary'                     AS source,
    FALSE AS processed_to_silver,
    ingested_at
FROM hcs_raw.cms_formulary
WHERE response_status = 200
  AND ingested_at BETWEEN @start_dt AND @end_dt;
