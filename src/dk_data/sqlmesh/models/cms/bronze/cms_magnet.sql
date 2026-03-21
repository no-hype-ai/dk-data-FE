-- SQLMesh Model: Bronze CMS Magnet Hospital Designations
-- Normalizes raw Magnet designation data to typed Bronze columns
-- Part of: 016-cms-puf-datasource-integration (Phase 3 — Facility MVP)

MODEL (
    name hcs_bronze.cms_magnet,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (facility_id))),
    grain (facility_id)
);

SELECT
    TRIM(facility_id)::TEXT                     AS facility_id,
    UPPER(TRIM(facility_name))                  AS facility_name,
    UPPER(TRIM(city))                           AS city,
    UPPER(TRIM(state))                          AS state,
    designation_date::DATE                      AS designation_date,
    expiration_date::DATE                       AS expiration_date,
    _loaded_at,
    _source_file,
    _source_hash
FROM hcs_raw.cms_magnet
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
