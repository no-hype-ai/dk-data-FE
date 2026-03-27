-- SQLMesh Model: Bronze CMS Imaging PUF
-- Typed pass-through from hcs_raw.cms_imaging_puf
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_imaging_puf,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (npi, hcpcs_cd, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (npi, hcpcs_cd, _source_year))
    ),
    grain (npi, hcpcs_cd, _source_year)
);

SELECT
    id::BIGINT,
    npi::TEXT,
    provider_last_org_name::TEXT,
    provider_city::TEXT,
    provider_state::TEXT,
    provider_zip5::TEXT,
    provider_type::TEXT,
    hcpcs_cd::TEXT,
    hcpcs_desc::TEXT,
    tot_benes::INTEGER,
    tot_srvcs::INTEGER,
    tot_mdcr_alowd_amt::NUMERIC,
    avg_mdcr_alowd_amt::NUMERIC,
    avg_mdcr_pymt_amt::NUMERIC,
    avg_mdcr_stdzd_amt::NUMERIC,
    _source_year::INTEGER,
    _source_hash::TEXT,
    _source_file::TEXT,
    _loaded_at::TIMESTAMPTZ,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_imaging_puf;
