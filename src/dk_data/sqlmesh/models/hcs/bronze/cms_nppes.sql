-- SQLMesh Model: Bronze CMS NPPES National Provider Identifier Registry
-- Typed pass-through from hcs_raw.cms_nppes
-- Feature: 019-cms-puf-platform-reconciliation (T012)

MODEL (
    name hcs_bronze.cms_nppes,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (npi, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (npi, _source_year))
    ),
    grain (npi, _source_year)
);

SELECT
    id,
    npi,
    entity_type_code,
    provider_last_name,
    provider_first_name,
    provider_organization_name,
    provider_business_mailing_address_city_name,
    provider_business_mailing_address_state_name,
    provider_business_mailing_address_postal_code,
    healthcare_provider_taxonomy_code_1,
    healthcare_provider_taxonomy_code_2,
    provider_business_mailing_address_telephone_number,
    npi_deactivation_date,
    npi_reactivation_date,
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_nppes;
