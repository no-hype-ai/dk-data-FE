-- SQLMesh Model: Bronze OpenFDA Device PMA
-- Transforms raw OpenFDA /device/pma responses into typed bronze rows.
-- Grain: (pma_number, supplement_number)

MODEL (
    name dev_bronze.openfda_device_pma,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (pma_number, supplement_number)
    ),
    cron '@weekly',
    audits (
        not_null(columns := (pma_number))
    ),
    grain (pma_number, supplement_number)
);

SELECT
    gen_random_uuid()                                       AS id,

    rec->>'pma_number'                                      AS pma_number,
    COALESCE(rec->>'supplement_number', '0')                AS supplement_number,

    rec->>'applicant'                                       AS applicant,
    rec->>'address_1'                                       AS address_1,
    rec->>'address_2'                                       AS address_2,
    rec->>'city'                                            AS city,
    rec->>'state'                                           AS state,
    rec->>'zip_code'                                        AS zip_code,

    CASE WHEN rec->>'date_received' ~ '^\d{4}-\d{2}-\d{2}$'
        THEN (rec->>'date_received')::DATE ELSE NULL END    AS date_received,
    CASE WHEN rec->>'decision_date' ~ '^\d{4}-\d{2}-\d{2}$'
        THEN (rec->>'decision_date')::DATE ELSE NULL END    AS decision_date,

    rec->>'decision_code'                                   AS decision_code,
    rec->>'ao_statement'                                    AS ao_statement,
    rec->>'advisory_committee'                              AS advisory_committee,
    rec->>'expedited_review_flag'                           AS expedited_review_flag,

    rec->>'supplement_type'                                 AS supplement_type,
    rec->>'supplement_reason'                               AS supplement_reason,

    rec->>'device_name'                                     AS device_name,
    rec->>'generic_name'                                    AS generic_name,
    rec->>'trade_name'                                      AS trade_name,
    rec->>'product_code'                                    AS product_code,

    rec->'openfda'->'device_name'->>0                       AS openfda_device_name,
    rec->'openfda'->'device_class'->>0                      AS openfda_device_class,
    rec->'openfda'->'regulation_number'->>0                 AS openfda_regulation_number,
    rec->'openfda'->'medical_specialty_description'->>0     AS openfda_medical_specialty_description,
    rec->'openfda'->'fei_number'::JSONB                     AS openfda_fei_number,
    rec->'openfda'->'registration_number'::JSONB            AS openfda_registration_number,

    rec                                                     AS raw_json,
    dev_raw.openfda_device_pma.id::TEXT                     AS raw_source_id,
    'openfda_device_pma'                                    AS source,
    request_timestamp,
    request_timestamp                                       AS source_updated_at,
    FALSE                                                   AS processed_to_silver,
    NOW()                                                   AS created_at

FROM dev_raw.openfda_device_pma,
     jsonb_array_elements(response_body->'results') AS rec
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND rec->>'pma_number' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
