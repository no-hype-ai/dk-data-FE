-- SQLMesh Model: Bronze CMS Home Health Agency PUF
-- Typed pass-through from hcs_raw.cms_home_health
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_home_health,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (provider_id, hh_srvc_cd, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (provider_id, _source_year))
    ),
    grain (provider_id, hh_srvc_cd, _source_year)
);

SELECT
    id::BIGINT,
    provider_id::TEXT,
    provider_name::TEXT,
    provider_city::TEXT,
    provider_state::TEXT,
    provider_zip5::TEXT,
    hh_srvc_cd::TEXT,
    hh_srvc_desc::TEXT,
    tot_epsd_stay::INTEGER,
    tot_benes::INTEGER,
    avg_hh_mdcr_pymt_amt::NUMERIC,
    avg_hh_outlier_pymt::NUMERIC,
    avg_age::NUMERIC,
    female_pct::NUMERIC,
    dual_pct::NUMERIC,
    _source_year::INTEGER,
    _source_hash::TEXT,
    _source_file::TEXT,
    _loaded_at::TIMESTAMPTZ,
    FALSE AS processed_to_silver,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_home_health;
