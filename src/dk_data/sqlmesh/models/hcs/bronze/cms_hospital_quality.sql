-- SQLMesh Model: Bronze CMS Hospital Quality Star Ratings
-- Extracts typed columns from JSONB response_body
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_hospital_quality,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key facility_id
    ),
    cron '@daily',
    audits (not_null(columns := (facility_id))),
    grain (facility_id)
);

SELECT
    response_body->>'facility_id'                       AS facility_id,
    response_body->>'facility_name'                     AS facility_name,
    (response_body->>'overall_rating')::INTEGER         AS overall_rating,
    (response_body->>'mortality_rating')::INTEGER       AS mortality_rating,
    (response_body->>'safety_rating')::INTEGER          AS safety_rating,
    (response_body->>'readmission_rating')::INTEGER     AS readmission_rating,
    (response_body->>'patient_experience_rating')::INTEGER AS patient_experience_rating,
    (response_body->>'timeliness_rating')::INTEGER      AS timeliness_rating,
    response_body                                       AS raw_json,
    id                                                  AS raw_source_id,
    'cms_hospital_quality'                              AS source,
    FALSE AS processed_to_silver,
    ingested_at
FROM hcs_raw.cms_hospital_quality
WHERE response_status = 200
  AND ingested_at BETWEEN @start_dt AND @end_dt;
