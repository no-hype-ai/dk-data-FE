-- SQLMesh Model: Bronze CMS Outpatient PUF
-- Normalizes raw Medicare Outpatient PUF data to typed Bronze columns
-- Part of: 016-cms-puf-datasource-integration (Phase 3 — Facility MVP)

MODEL (
    name hcs_bronze.cms_outpatient_puf,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (provider_id, apc_code))),
    grain (provider_id, apc_code)
);

SELECT
    TRIM(provider_id)::TEXT                     AS provider_id,
    TRIM(apc_code)::TEXT                        AS apc_code,
    NULLIF(TRIM(total_services), '')::INTEGER   AS total_services,
    NULLIF(TRIM(avg_total_payments), '')::NUMERIC AS avg_total_payments,
    EXTRACT(YEAR FROM _loaded_at)::INTEGER      AS year,
    _loaded_at,
    _source_file,
    _source_hash
FROM hcs_raw.cms_outpatient_puf
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
