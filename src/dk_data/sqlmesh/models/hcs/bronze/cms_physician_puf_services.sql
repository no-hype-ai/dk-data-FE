-- SQLMesh Model: hcs_bronze.cms_physician_puf_services
-- Per-HCPCS line items from the Medicare Physician PUF (Item 27c)
-- Feature: 006-claims-engine-data-gaps

MODEL (
    name hcs_bronze.cms_physician_puf_services,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (npi, hcpcs_code)
    ),
    cron '@weekly',
    grain (npi, hcpcs_code)
);

SELECT
    r.id AS raw_id,
    r.npi,
    r.hcpcs_code,
    r.hcpcs_description,
    r.place_of_service,
    r.number_of_services,
    r.number_of_medicare_beneficiaries,
    r.number_of_distinct_medicare_beneficiary_per_day_services,
    r.average_medicare_allowed_amt,
    r.average_submitted_charge_amt,
    r.average_medicare_payment_amt,
    r.average_medicare_standardized_amt,
    r.ingested_at
FROM hcs_raw.cms_physician_puf_services r
WHERE r.ingested_at BETWEEN @start_dt AND @end_dt
