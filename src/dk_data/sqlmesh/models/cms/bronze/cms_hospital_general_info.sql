-- SQLMesh Model: Bronze CMS Hospital General Information
-- Normalizes raw Hospital General Information data to typed Bronze columns
-- Part of: 016-cms-puf-datasource-integration (Phase 3 — Facility MVP)

MODEL (
    name hcs_bronze.cms_hospital_general_info,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (provider_id))),
    grain (provider_id)
);

SELECT
    TRIM(provider_id)::TEXT                     AS provider_id,
    UPPER(TRIM(hospital_name))                  AS hospital_name,
    TRIM(address)                               AS address,
    UPPER(TRIM(city))                           AS city,
    UPPER(TRIM(state))                          AS state,
    TRIM(zip_code)::TEXT                        AS zip_code,
    UPPER(TRIM(hospital_type))                  AS hospital_type,
    UPPER(TRIM(ownership))                      AS ownership,
    overall_rating::INTEGER                     AS overall_rating,
    _loaded_at,
    _source_file,
    _source_hash
FROM hcs_raw.cms_hospital_general_info
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
