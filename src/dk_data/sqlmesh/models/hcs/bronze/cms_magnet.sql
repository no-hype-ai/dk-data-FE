-- SQLMesh Model: Bronze CMS Magnet Hospital Designations
-- Extracts typed columns from JSONB response_body
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_magnet,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (facility_name, city, state)
    ),
    cron '@daily',
    audits (not_null(columns := (facility_name))),
    grain (facility_name, city, state)
);

SELECT
    response_body->>'facility_name'                     AS facility_name,
    response_body->>'city'                              AS city,
    response_body->>'state'                             AS state,
    response_body->>'designation_year'                  AS designation_year,
    CASE
        WHEN (response_body->>'designation_year') ~ '^\d{4}$'
        THEN ((response_body->>'designation_year') || '-01-01')::DATE
        ELSE NULL
    END                                                 AS designation_date,
    response_body                                       AS raw_json,
    id                                                  AS raw_source_id,
    'cms_magnet'                                        AS source,
    FALSE AS processed_to_silver,
    ingested_at
FROM hcs_raw.cms_magnet
WHERE response_status = 200
  AND ingested_at BETWEEN @start_dt AND @end_dt;
