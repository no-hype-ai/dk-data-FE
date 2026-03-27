-- SQLMesh Model: Bronze CMS DDInter Drug Interactions
-- Extracts typed columns from JSONB response_body
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_ddinter,
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
    response_body->>'interaction_type'  AS interaction_type,
    response_body->>'severity'          AS severity,
    response_body->>'description'       AS description,
    response_body                       AS raw_json,
    id                                  AS raw_source_id,
    'cms_ddinter'                       AS source,
    ingested_at
FROM hcs_raw.cms_ddinter
WHERE response_status = 200
  AND ingested_at BETWEEN @start_dt AND @end_dt;
