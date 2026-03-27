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
    id::BIGINT,
    npi::TEXT,
    hcpcs_code::TEXT,
    hcpcs_description::TEXT,
    hcpcs_drug_ind::TEXT,
    place_of_service::TEXT,
    line_srvc_cnt::NUMERIC,
    bene_unique_cnt::INTEGER,
    bene_day_srvc_cnt::INTEGER,
    average_submitted_chrg_amt::NUMERIC,
    average_medicare_allowed_amt::NUMERIC,
    average_medicare_payment_amt::NUMERIC,
    average_medicare_stnd_amt::NUMERIC,
    _source_year::INTEGER,
    _source_hash::TEXT,
    _source_file::TEXT,
    _loaded_at::TIMESTAMPTZ,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_physician_puf_services;
