-- SQLMesh Model: Bronze CMS NPPES Provider Registry
-- Extracts typed columns from JSONB response_body
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_nppes,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (npi))),
    grain (npi)
);

SELECT
    response_body->>'npi'                   AS npi,
    response_body->>'entity_type_code'      AS entity_type_code,
    response_body->>'provider_organization_name' AS provider_organization_name,
    response_body->>'provider_last_name'    AS provider_last_name,
    response_body->>'provider_first_name'   AS provider_first_name,
    response_body->>'provider_credential_text' AS provider_credential_text,
    response_body->>'provider_enumeration_date' AS provider_enumeration_date,
    response_body->>'provider_gender_code'  AS provider_gender_code,
    response_body->>'provider_business_practice_location_address_state_name' AS practice_state,
    response_body->>'provider_business_practice_location_address_postal_code' AS practice_zip,
    response_body->>'provider_business_practice_location_address_telephone_number' AS practice_phone,
    response_body->>'healthcare_provider_taxonomy_code_1' AS taxonomy_code_1,
    response_body                           AS raw_json,
    id                                      AS raw_source_id,
    'cms_nppes'                             AS source,
    ingested_at
FROM hcs_raw.cms_nppes
WHERE response_status = 200
  AND ingested_at BETWEEN @start_dt AND @end_dt;
