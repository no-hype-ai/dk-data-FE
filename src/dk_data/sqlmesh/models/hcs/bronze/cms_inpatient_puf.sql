-- SQLMesh Model: Bronze CMS Inpatient PUF (All DRGs)
-- Typed pass-through from hcs_raw.cms_inpatient_puf
-- Feature: 019-cms-puf-platform-reconciliation (T012)

MODEL (
    name hcs_bronze.cms_inpatient_puf,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (_source_hash, provider_id, drg_definition, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (_source_year))
    ),
    grain (_source_hash, provider_id, drg_definition, _source_year)
);

SELECT
    id::BIGINT,
    -- DRG identifiers (newer format has both code and description separately)
    drg_cd::TEXT,
    drg_definition::TEXT,
    -- Provider identifiers (TEXT — CMS provider IDs are CCNs with leading zeros)
    provider_id::TEXT,
    provider_name::TEXT,
    provider_street_address::TEXT,
    provider_city::TEXT,
    provider_state::TEXT,
    provider_state_fips::TEXT,
    provider_zip_code::TEXT,
    provider_ruca::TEXT,
    hospital_referral_region_desc::TEXT,
    -- Metrics
    total_discharges::INTEGER,
    average_covered_charges::NUMERIC,
    average_total_payments::NUMERIC,
    average_medicare_payments::NUMERIC,
    _source_year::INTEGER,
    _source_hash::TEXT,
    _source_file::TEXT,
    _loaded_at::TIMESTAMPTZ,
    FALSE AS processed_to_silver,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_inpatient_puf;
