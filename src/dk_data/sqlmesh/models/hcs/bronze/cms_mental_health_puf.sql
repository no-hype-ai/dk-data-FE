-- SQLMesh Model: Bronze CMS Mental Health PUF
-- Typed pass-through from hcs_raw.cms_mental_health_puf
-- Feature: 019-cms-puf-platform-reconciliation
--
-- Raw columns: npi (TEXT), provider_last_org_name, provider_first_name,
--   provider_city, provider_state, provider_zip5, provider_type,
--   hcpcs_cd, hcpcs_desc, mh_srvc_ind (BOOLEAN),
--   tot_benes (INTEGER), tot_srvcs (NUMERIC),
--   tot_mdcr_alowd_amt (NUMERIC), avg_mdcr_alowd_amt (NUMERIC),
--   avg_mdcr_pymt_amt (NUMERIC), avg_mdcr_stdzd_amt (NUMERIC)

MODEL (
    name hcs_bronze.cms_mental_health_puf,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (npi, hcpcs_cd, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (_source_year))
    ),
    grain (npi, hcpcs_cd, _source_year)
);

SELECT
    id::BIGINT,
    npi::TEXT,
    provider_last_org_name::TEXT,
    provider_first_name::TEXT,
    provider_city::TEXT,
    provider_state::TEXT,
    provider_zip5::TEXT,
    provider_type::TEXT,
    hcpcs_cd::TEXT,
    hcpcs_desc::TEXT,
    mh_srvc_ind::BOOLEAN,
    tot_benes::INTEGER,
    tot_srvcs::NUMERIC,
    tot_mdcr_alowd_amt::NUMERIC,
    avg_mdcr_alowd_amt::NUMERIC,
    avg_mdcr_pymt_amt::NUMERIC,
    avg_mdcr_stdzd_amt::NUMERIC,
    _source_year::INTEGER,
    _source_hash::TEXT,
    _source_file::TEXT,
    _loaded_at::TIMESTAMPTZ,
    FALSE AS processed_to_silver,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_mental_health_puf;
