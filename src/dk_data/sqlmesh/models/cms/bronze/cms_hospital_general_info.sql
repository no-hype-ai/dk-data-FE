-- SQLMesh Model: Bronze CMS Hospital General Information
-- Extracts typed columns from JSONB response_body
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_hospital_general_info,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (facility_id))),
    grain (facility_id)
);

SELECT
    response_body->>'facility_id'       AS facility_id,
    response_body->>'facility_name'     AS facility_name,
    response_body->>'address'           AS address,
    response_body->>'city'              AS city,
    response_body->>'state'             AS state,
    response_body->>'zip'               AS zip_code,
    response_body->>'county'            AS county,
    response_body->>'phone'             AS phone,
    response_body->>'hospital_type'     AS hospital_type,
    response_body->>'ownership'         AS ownership,
    response_body->>'emergency_services' AS emergency_services,
    response_body                       AS raw_json,
    id                                  AS raw_source_id,
    'cms_hospital_general_info'         AS source,
    ingested_at
FROM hcs_raw.cms_hospital_general_info
WHERE response_status = 200
  AND ingested_at BETWEEN @start_dt AND @end_dt;
