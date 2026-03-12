-- SQLMesh Model: Bronze CMS NPPES
-- Normalizes raw NPPES provider identity data to typed Bronze columns
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name bronze.cms_nppes,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (npi))),
    grain (npi)
);

SELECT
    TRIM(npi)::TEXT                         AS npi,
    UPPER(TRIM(entity_type))                AS entity_type,
    UPPER(TRIM(name_first))                 AS name_first,
    UPPER(TRIM(name_last))                  AS name_last,
    UPPER(TRIM(name_org))                   AS name_org,
    UPPER(TRIM(credential))                 AS credential,
    TRIM(taxonomy_code)::TEXT               AS taxonomy_code,
    UPPER(TRIM(practice_address_1))         AS practice_address_1,
    UPPER(TRIM(practice_city))              AS practice_city,
    UPPER(TRIM(practice_state))             AS practice_state,
    TRIM(practice_zip)::TEXT                AS practice_zip,
    TRIM(practice_phone)::TEXT              AS practice_phone,
    enumeration_date::DATE                  AS enumeration_date,
    last_updated::DATE                      AS last_updated,
    deactivation_date::DATE                 AS deactivation_date,
    UPPER(TRIM(gender))                     AS gender,
    _loaded_at,
    _source_file,
    _source_hash
FROM raw.cms_nppes
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
