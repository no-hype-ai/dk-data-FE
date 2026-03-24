-- SQLMesh Model: Bronze CMS Provider of Services (POS)
-- Extracts typed columns from JSONB response_body
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_pos,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (ccn))),
    grain (ccn)
);

SELECT
    response_body->>'ccn'               AS ccn,
    response_body->>'facility_name'     AS facility_name,
    response_body->>'street_address'    AS street_address,
    response_body->>'city'              AS city,
    response_body->>'state'             AS state,
    response_body->>'zip_code'          AS zip_code,
    response_body->>'provider_type'     AS provider_type,
    (response_body->>'beds')::INTEGER   AS beds,
    response_body->>'ownership_type'    AS ownership_type,
    response_body                       AS raw_json,
    id                                  AS raw_source_id,
    'cms_pos'                           AS source,
    ingested_at
FROM hcs_raw.cms_pos
WHERE response_status = 200
  AND ingested_at BETWEEN @start_dt AND @end_dt;
