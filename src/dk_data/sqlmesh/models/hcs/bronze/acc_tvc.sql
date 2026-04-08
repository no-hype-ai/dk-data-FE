-- SQLMesh Model: Bronze ACC/TVC Certification
-- Transforms raw hcs_raw.acc_tvc_certification data to Bronze typed columns.
-- Source: hcs_raw.acc_tvc_certification (loaded by acc_tvc fetcher or manual CSV)
-- Part of: 015-assessment-dashboard-integration
--
-- Raw table columns (init_database.sql → migrated to hcs_raw via migration 099):
--   id SERIAL, facility_name, facility_address, city, state, zip_code,
--   certification_type, certification_date DATE, expiration_date DATE,
--   _loaded_at TIMESTAMP, _source_file, _source_hash
--
-- Grain: (facility_name, state, certification_type) — no numeric facility ID in raw

MODEL (
    name hcs_bronze.acc_tvc,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (facility_name, state, certification_type)
    ),
    cron '@daily',
    audits (
        not_null(columns := (facility_name, state, certification_type))
    ),
    grain (facility_name, state, certification_type)
);

SELECT
    gen_random_uuid()           AS id,
    r.facility_name::TEXT       AS facility_name,
    r.facility_address::TEXT    AS facility_address,
    r.city::TEXT                AS city,
    r.state::TEXT               AS state,
    r.zip_code::TEXT            AS zip_code,
    r.certification_type::TEXT  AS certification_type,
    r.certification_date::DATE  AS certification_date,
    r.expiration_date::DATE     AS expiration_date,
    r._loaded_at::TIMESTAMPTZ   AS _loaded_at,
    r._source_file::TEXT        AS _source_file,
    r._source_hash::TEXT        AS _source_hash,
    'acc_tvc'                   AS source,
    r._loaded_at::TIMESTAMPTZ   AS source_updated_at,
    FALSE                       AS processed_to_silver,
    NOW()                       AS created_at

FROM hcs_raw.acc_tvc_certification r
WHERE
    r.facility_name IS NOT NULL
    AND r._loaded_at BETWEEN @start_dt AND @end_dt;
