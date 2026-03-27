-- SQLMesh Model: Bronze CMS Referring Providers
-- Typed pass-through from hcs_raw.cms_referring_providers
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_referring_providers,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (referring_npi, referred_to_npi, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (referring_npi, referred_to_npi, _source_year))
    ),
    grain (referring_npi, referred_to_npi, _source_year)
);

SELECT
    id,
    referring_npi,
    referred_to_npi,
    provider_last_org_name,
    provider_first_name,
    provider_type,
    provider_city,
    provider_state,
    referral_count,
    unique_benes,
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_referring_providers;
