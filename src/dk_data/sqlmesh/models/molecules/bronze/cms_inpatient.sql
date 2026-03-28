-- SQLMesh Model: Bronze CMS Inpatient PUF
-- Transforms flat hcs_raw.cms_inpatient_puf table to Bronze typed columns.
-- Source: hcs_raw.cms_inpatient_puf (loaded by cms_inpatient_puf.py CronJob)
-- Part of: 015-assessment-dashboard-integration / 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_inpatient,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@daily',
    audits (
        not_null(columns := (provider_id))
    ),
    grain record_id
);

SELECT
    gen_random_uuid() AS id,

    -- Record identifiers
    COALESCE(
        provider_id || '_' || drg_cd || '_' || _source_year::TEXT,
        gen_random_uuid()::TEXT
    ) AS record_id,
    provider_id::TEXT AS provider_id,
    drg_cd::TEXT AS drg_code,
    total_discharges::INTEGER AS total_discharges,
    average_covered_charges::NUMERIC AS avg_charges,
    average_total_payments::NUMERIC AS avg_payments,
    average_medicare_payments::NUMERIC AS avg_medicare_payments,
    _source_year::TEXT AS fiscal_year,

    -- Raw source tracking
    id::BIGINT AS raw_source_id,
    'cms_inpatient_puf' AS source,
    _loaded_at AS request_timestamp,
    _loaded_at AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM hcs_raw.cms_inpatient_puf
WHERE
    provider_id IS NOT NULL
    AND _loaded_at BETWEEN @start_dt AND @end_dt;
