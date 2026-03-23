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
    audits (not_null(columns := (facility_name))),
    grain (facility_name, city, state)
);

SELECT
    md5(TRIM(facility_name) || TRIM(city) || TRIM(state))::TEXT AS facility_id,
    UPPER(TRIM(facility_name))                  AS facility_name,
    UPPER(TRIM(city))                           AS city,
    UPPER(TRIM(state))                          AS state,
    CASE WHEN designation_year ~ '^\d{4}$' THEN (designation_year || '-01-01')::DATE ELSE NULL END AS designation_date,
    NULL::DATE                                  AS expiration_date,
    _loaded_at,
    _source_file,
    _source_hash
FROM hcs_raw.cms_magnet
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
