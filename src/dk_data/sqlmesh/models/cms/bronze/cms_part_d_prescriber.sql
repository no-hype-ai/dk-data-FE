-- SQLMesh Model: Bronze CMS Part D Prescriber
-- Normalizes raw Part D Prescriber PUF data to typed Bronze columns
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_part_d_prescriber,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (npi, drug_name, year))),
    grain (npi, drug_name, year)
);

SELECT
    TRIM(npi)::TEXT                                     AS npi,
    UPPER(TRIM(drug_name))                              AS drug_name,
    UPPER(TRIM(generic_name))                           AS generic_name,
    COALESCE(total_claim_count, 0)::INTEGER             AS total_claims,
    COALESCE(total_30_day_fill_count, 0)::NUMERIC       AS total_30_day_fills,
    COALESCE(total_drug_cost, 0)::NUMERIC(12,2)         AS total_drug_cost,
    COALESCE(total_beneficiary_count, 0)::INTEGER       AS total_beneficiaries,
    year::INTEGER                                       AS year,
    _loaded_at,
    _source_file,
    _source_hash
FROM hcs_raw.cms_part_d_prescriber
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
