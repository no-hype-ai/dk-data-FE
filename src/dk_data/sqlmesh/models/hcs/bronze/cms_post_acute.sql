-- SQLMesh Model: Bronze CMS Post-Acute Care
-- Extracts typed columns from JSONB response_body
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_post_acute,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (ccn, year)
    ),
    cron '@daily',
    audits (not_null(columns := (ccn))),
    grain (ccn, year)
);

SELECT
    response_body->>'ccn'                                   AS ccn,
    response_body->>'provider_name'                         AS provider_name,
    response_body->>'provider_type'                         AS provider_type,
    (response_body->>'total_episodes')::INTEGER             AS total_episodes,
    (response_body->>'avg_episode_payment')::NUMERIC         AS avg_episode_payment,
    (response_body->>'readmission_rate')::NUMERIC(6,4)      AS readmission_rate,
    (response_body->>'year')::INTEGER                       AS year,
    response_body                                           AS raw_json,
    id                                                      AS raw_source_id,
    'cms_post_acute'                                        AS source,
    FALSE AS processed_to_silver,
    ingested_at
FROM hcs_raw.cms_post_acute
WHERE response_status = 200
  AND ingested_at BETWEEN @start_dt AND @end_dt;
