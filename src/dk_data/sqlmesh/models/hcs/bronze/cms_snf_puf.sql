-- SQLMesh Model: Bronze CMS Skilled Nursing Facility PUF
-- Typed pass-through from hcs_raw.cms_snf_puf
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_snf_puf,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (provider_id, rug_cd, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (provider_id, _source_year))
    ),
    grain (provider_id, rug_cd, _source_year)
);

SELECT
    id::BIGINT,
    provider_id::TEXT,
    provider_name::TEXT,
    provider_city::TEXT,
    provider_state::TEXT,
    provider_zip5::TEXT,
    rug_cd::TEXT,
    rug_desc::TEXT,
    tot_benes::INTEGER,
    tot_cvrd_days::INTEGER,
    avg_cvrd_days::NUMERIC,
    tot_mdcr_alowd_amt::NUMERIC,
    avg_mdcr_alowd_amt::NUMERIC,
    tot_mdcr_pymt_amt::NUMERIC,
    avg_mdcr_pymt_amt::NUMERIC,
    _source_year::INTEGER,
    _source_hash::TEXT,
    _source_file::TEXT,
    _loaded_at::TIMESTAMPTZ,
    FALSE AS processed_to_silver,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_snf_puf;
