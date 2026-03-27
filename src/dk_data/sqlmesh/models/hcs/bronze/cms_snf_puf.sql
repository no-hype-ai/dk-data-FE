-- SQLMesh Model: Bronze CMS Skilled Nursing Facility PUF
-- Typed pass-through from hcs_raw.cms_snf_puf
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_snf_puf,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (provider_id, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (provider_id, _source_year))
    ),
    grain (provider_id, _source_year)
);

SELECT
    id,
    provider_id,
    provider_name,
    address,
    city,
    state,
    zip_code,
    snf_type,
    ownership_type,
    total_episodes,
    total_medicare_payment,
    average_payment_per_episode,
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_snf_puf;
