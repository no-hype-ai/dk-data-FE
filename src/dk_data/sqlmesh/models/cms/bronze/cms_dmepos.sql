-- SQLMesh Model: Bronze CMS DMEPOS Utilization
-- Normalizes raw Durable Medical Equipment utilization to typed Bronze columns
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name bronze.cms_dmepos,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (npi, hcpcs_code))),
    grain (npi, hcpcs_code)
);

SELECT
    TRIM(npi)::TEXT                             AS npi,
    TRIM(hcpcs_code)::TEXT                      AS hcpcs_code,
    COALESCE(total_services, 0)::INTEGER        AS total_services,
    COALESCE(total_beneficiaries, 0)::INTEGER   AS total_beneficiaries,
    COALESCE(avg_submitted_charge, 0)::NUMERIC(10,2) AS avg_submitted_charge,
    COALESCE(avg_medicare_payment, 0)::NUMERIC(10,2) AS avg_medicare_payment,
    year::INTEGER                               AS year,
    _loaded_at,
    _source_file,
    _source_hash
FROM raw.cms_dmepos
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
