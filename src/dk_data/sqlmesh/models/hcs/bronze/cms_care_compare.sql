-- SQLMesh Model: Bronze CMS Care Compare
-- Extracts typed columns from JSONB response_body (facility data)
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_care_compare,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (facility_id))),
    grain (facility_id)
);

SELECT
    response_body->>'facility_id'           AS facility_id,
    response_body->>'facility_name'         AS facility_name,
    response_body->>'address'               AS address,
    response_body->>'city'                  AS city,
    response_body->>'state'                 AS state,
    response_body->>'zip_code'              AS zip_code,
    response_body->>'county_name'           AS county_name,
    response_body->>'phone_number'          AS phone_number,
    response_body->>'hospital_type'         AS hospital_type,
    response_body->>'hospital_ownership'    AS hospital_ownership,
    response_body->>'emergency_services'    AS emergency_services,
    NULLIF(response_body->>'hospital_overall_rating', 'Not Available')::INTEGER AS overall_rating,
    response_body                           AS raw_json,
    id                                      AS raw_source_id,
    'cms_care_compare'                      AS source,
    FALSE AS processed_to_silver,
    ingested_at
FROM hcs_raw.cms_care_compare
WHERE response_status = 200
  AND ingested_at BETWEEN @start_dt AND @end_dt;
