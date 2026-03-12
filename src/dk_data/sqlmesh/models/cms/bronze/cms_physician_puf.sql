-- SQLMesh Model: Bronze CMS Physician PUF
-- Normalizes raw Medicare Physician & Other Supplier PUF data to typed Bronze columns
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name bronze.cms_physician_puf,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (npi, hcpcs_code, year))),
    grain (npi, hcpcs_code, year)
);

SELECT
    TRIM(npi)::TEXT                                     AS npi,
    UPPER(TRIM(hcpcs_code))::TEXT                       AS hcpcs_code,
    UPPER(TRIM(hcpcs_description))                      AS hcpcs_description,
    COALESCE(line_srvc_cnt, 0)::NUMERIC                 AS line_srvc_cnt,
    COALESCE(bene_unique_cnt, 0)::INTEGER               AS bene_unique_cnt,
    COALESCE(avg_medicare_payment_amt, 0)::NUMERIC(12,2) AS avg_medicare_payment_amt,
    year::INTEGER                                       AS year,
    _loaded_at,
    _source_file,
    _source_hash
FROM raw.cms_physician_puf
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
