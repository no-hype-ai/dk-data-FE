-- SQLMesh Model: Bronze CMS Hospital Affiliation
-- Extracts typed columns from JSONB response_body
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_hospital_affiliation,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (npi))),
    grain (npi, facility_affiliations_certification_number)
);

SELECT
    response_body->>'npi'                                       AS npi,
    response_body->>'ind_pac_id'                                AS ind_pac_id,
    response_body->>'provider_last_name'                        AS provider_last_name,
    response_body->>'provider_first_name'                       AS provider_first_name,
    response_body->>'provider_middle_name'                      AS provider_middle_name,
    response_body->>'facility_type'                             AS facility_type,
    response_body->>'facility_affiliations_certification_number' AS facility_affiliations_certification_number,
    response_body->>'facility_type_certification_number'        AS facility_type_certification_number,
    response_body                                               AS raw_json,
    id                                                          AS raw_source_id,
    'cms_hospital_affiliation'                                  AS source,
    FALSE AS processed_to_silver,
    ingested_at
FROM hcs_raw.cms_hospital_affiliation
WHERE response_status = 200
  AND ingested_at BETWEEN @start_dt AND @end_dt;
