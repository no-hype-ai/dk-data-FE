-- SQLMesh Model: Bronze CMS Stabilis IV Drug Compatibility
-- Extracts typed columns from JSONB response_body
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_stabilis,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (drug_a, drug_b))),
    grain (drug_a, drug_b)
);

SELECT
    response_body->>'drug_a'            AS drug_a,
    response_body->>'drug_b'            AS drug_b,
    response_body->>'compatibility'     AS compatibility,
    response_body->>'solvent'           AS solvent,
    response_body->>'concentration'     AS concentration,
    response_body->>'reference'         AS reference,
    response_body                       AS raw_json,
    id                                  AS raw_source_id,
    'cms_stabilis'                      AS source,
    FALSE AS processed_to_silver,
    ingested_at
FROM hcs_raw.cms_stabilis
WHERE response_status = 200
  AND ingested_at BETWEEN @start_dt AND @end_dt;
