-- SQLMesh Model: Bronze CMS Provider of Services (POS)
-- Normalizes raw POS facility data to typed Bronze columns
-- Part of: 016-cms-puf-datasource-integration (Phase 3 — Facility MVP)

MODEL (
    name bronze.cms_pos,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (ccn))),
    grain (ccn)
);

SELECT
    TRIM(ccn)::TEXT                             AS ccn,
    UPPER(TRIM(facility_name))                  AS facility_name,
    UPPER(TRIM(facility_type))                  AS facility_type,
    TRIM(address)                               AS address,
    UPPER(TRIM(city))                           AS city,
    UPPER(TRIM(state))                          AS state,
    TRIM(zip_code)::TEXT                        AS zip_code,
    bed_count::INTEGER                          AS bed_count,
    _loaded_at,
    _source_file,
    _source_hash
FROM raw.cms_pos
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
