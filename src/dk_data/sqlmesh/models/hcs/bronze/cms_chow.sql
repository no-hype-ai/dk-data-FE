-- SQLMesh Model: Bronze CMS Change of Ownership (CHOW)
-- Extracts typed columns from JSONB response_body
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_chow,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (ccn, effective_date))),
    grain (ccn, effective_date)
);

SELECT
    response_body->>'ccn'               AS ccn,
    response_body->>'previous_owner'    AS previous_owner,
    response_body->>'new_owner'         AS new_owner,
    (response_body->>'effective_date')::DATE AS effective_date,
    response_body->>'provider_type'     AS provider_type,
    response_body                       AS raw_json,
    id                                  AS raw_source_id,
    'cms_chow'                          AS source,
    ingested_at
FROM hcs_raw.cms_chow
WHERE response_status = 200
  AND ingested_at BETWEEN @start_dt AND @end_dt;
