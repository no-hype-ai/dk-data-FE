-- SQLMesh Model: Bronze CMS Hospital Outpatient PUF
-- Typed pass-through from hcs_raw.cms_outpatient_puf
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_outpatient_puf,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (_source_hash, provider_id, apc, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (_source_year))
    ),
    grain (_source_hash, provider_id, apc, _source_year)
);

SELECT
    id::BIGINT,
    -- Provider identifiers (TEXT — CMS provider IDs are CCNs with leading zeros)
    provider_id::TEXT,
    provider_name::TEXT,
    provider_city::TEXT,
    provider_state::TEXT,
    provider_state_fips::TEXT,
    provider_zip_code::TEXT,
    provider_ruca::TEXT,
    -- APC identifiers
    apc::TEXT,
    apc_desc::TEXT,
    -- Metrics
    total_services::INTEGER,
    bene_cnt::INTEGER,
    comp_asgn_pymt_cnt::INTEGER,
    average_estimated_submitted_charges::NUMERIC,
    average_medicare_allowed_amt::NUMERIC,
    average_total_payments::NUMERIC,
    average_medicare_payments::NUMERIC,
    average_medicare_stnd_amt::NUMERIC,
    _source_year::INTEGER,
    _source_hash::TEXT,
    _source_file::TEXT,
    _loaded_at::TIMESTAMPTZ,
    FALSE AS processed_to_silver,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_outpatient_puf;
