-- SQLMesh Model: Bronze OpenFDA Device 510(k)
-- Transforms raw OpenFDA /device/510k responses into typed bronze rows.
-- Unnests response_body->'results' array; one row per 510(k) clearance record.
-- Feature: FDA medical devices ingestion (2026-04-21)
-- Grain: k_number

MODEL (
    name dev_bronze.openfda_device_510k,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key k_number
    ),
    cron '@weekly',
    audits (
        not_null(columns := (k_number))
    ),
    grain k_number
);

SELECT
    gen_random_uuid()                                       AS id,

    -- Natural key
    rec->>'k_number'                                        AS k_number,

    -- Applicant / company (resolved to company_id in silver via resolve_company)
    rec->>'applicant'                                       AS applicant,
    rec->>'contact'                                         AS contact,
    rec->>'address_1'                                       AS address_1,
    rec->>'address_2'                                       AS address_2,
    rec->>'city'                                            AS city,
    rec->>'state'                                           AS state,
    rec->>'country_code'                                    AS country_code,
    rec->>'zip_code'                                        AS zip_code,
    rec->>'postal_code'                                     AS postal_code,

    -- Dates (YYYY-MM-DD per OpenFDA 510k schema)
    CASE WHEN rec->>'date_received' ~ '^\d{4}-\d{2}-\d{2}$'
        THEN (rec->>'date_received')::DATE ELSE NULL END    AS date_received,
    CASE WHEN rec->>'decision_date' ~ '^\d{4}-\d{2}-\d{2}$'
        THEN (rec->>'decision_date')::DATE ELSE NULL END    AS decision_date,

    -- Decision
    rec->>'decision_code'                                   AS decision_code,
    rec->>'decision_description'                            AS decision_description,
    rec->>'clearance_type'                                  AS clearance_type,
    rec->>'third_party_flag'                                AS third_party_flag,
    rec->>'expedited_review_flag'                           AS expedited_review_flag,
    rec->>'statement_or_summary'                            AS statement_or_summary,

    -- Device
    rec->>'device_name'                                     AS device_name,
    rec->>'product_code'                                    AS product_code,

    -- Advisory committee (FDA review panel)
    rec->>'advisory_committee'                              AS advisory_committee,
    rec->>'advisory_committee_description'                  AS advisory_committee_description,
    rec->>'review_advisory_committee'                       AS review_advisory_committee,

    -- OpenFDA enrichment sub-object
    rec->'openfda'->'device_name'->>0                       AS openfda_device_name,
    rec->'openfda'->'device_class'->>0                      AS openfda_device_class,
    rec->'openfda'->'regulation_number'->>0                 AS openfda_regulation_number,
    rec->'openfda'->'medical_specialty_description'->>0     AS openfda_medical_specialty_description,
    rec->'openfda'->'fei_number'::JSONB                     AS openfda_fei_number,
    rec->'openfda'->'registration_number'::JSONB            AS openfda_registration_number,

    -- Raw tracking
    rec                                                     AS raw_json,
    dev_raw.openfda_device_510k.id::TEXT                    AS raw_source_id,
    'openfda_device_510k'                                   AS source,
    request_timestamp,
    request_timestamp                                       AS source_updated_at,
    FALSE                                                   AS processed_to_silver,
    NOW()                                                   AS created_at

FROM dev_raw.openfda_device_510k,
     jsonb_array_elements(response_body->'results') AS rec
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND rec->>'k_number' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
