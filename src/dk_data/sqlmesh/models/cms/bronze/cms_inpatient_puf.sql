-- SQLMesh Model: Bronze CMS Inpatient PUF
-- Normalizes raw Medicare Inpatient PUF data to typed Bronze columns
-- Part of: 016-cms-puf-datasource-integration (Phase 3 — Facility MVP)

MODEL (
    name bronze.cms_inpatient_puf,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (provider_id, drg_code))),
    grain (provider_id, drg_code)
);

SELECT
    TRIM(provider_id)::TEXT                     AS provider_id,
    TRIM(drg_code)::TEXT                        AS drg_code,
    total_discharges::INTEGER                   AS total_discharges,
    avg_covered_charges::NUMERIC                AS avg_covered_charges,
    avg_total_payments::NUMERIC                 AS avg_total_payments,
    avg_medicare_payments::NUMERIC              AS avg_medicare_payments,
    year::INTEGER                               AS year,
    _loaded_at,
    _source_file,
    _source_hash
FROM raw.cms_inpatient_puf
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
