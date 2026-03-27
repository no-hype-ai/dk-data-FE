-- SQLMesh Model: Bronze CMS Physician PUF by Provider and Service (HCPCS grain)
-- Typed pass-through from hcs_raw.cms_physician_puf_services
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_physician_puf_services,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (npi, hcpcs_code, place_of_service, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (npi, hcpcs_code, _source_year))
    ),
    grain (npi, hcpcs_code, place_of_service, _source_year)
);

SELECT
    id,
    npi,
    hcpcs_code,
    hcpcs_description,
    line_srvc_cnt,
    bene_unique_cnt,
    bene_day_srvc_cnt,
    average_submitted_chrg_amt,
    average_medicare_allowed_amt,
    average_medicare_payment_amt,
    place_of_service,
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_physician_puf_services;
