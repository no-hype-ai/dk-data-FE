-- SQLMesh Model: Bronze CMS Geographic Variation PUF
-- Extracts typed columns from JSONB response_body
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_geographic_variation,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (state, county))),
    grain (state, county)
);

SELECT
    response_body->>'state'                             AS state,
    response_body->>'county'                            AS county,
    (response_body->>'bene_count')::INTEGER             AS bene_count,
    (response_body->>'total_actual_costs')::NUMERIC(14,2) AS total_actual_costs,
    (response_body->>'per_capita_costs')::NUMERIC(10,2) AS per_capita_costs,
    (response_body->>'year')::INTEGER                   AS year,
    response_body                                       AS raw_json,
    id                                                  AS raw_source_id,
    'cms_geographic_variation'                          AS source,
    ingested_at
FROM hcs_raw.cms_geographic_variation
WHERE response_status = 200
  AND ingested_at BETWEEN @start_dt AND @end_dt;
