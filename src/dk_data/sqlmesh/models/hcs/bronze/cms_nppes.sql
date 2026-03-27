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
    id::BIGINT,
    npi::TEXT,
    entity_type_code::TEXT,
    -- Individual name fields (raw table has last/first/org; no middle name or credential text)
    provider_last_name::TEXT,
    provider_first_name::TEXT,
    -- Organization name
    provider_organization_name::TEXT,
    -- Mailing address (used by idn_hierarchy agent)
    provider_business_mailing_address_city_name::TEXT,
    provider_business_mailing_address_state_name::TEXT,
    provider_business_mailing_address_postal_code::TEXT,
    provider_business_mailing_address_telephone_number::TEXT,
    -- Taxonomy codes
    healthcare_provider_taxonomy_code_1::TEXT,
    healthcare_provider_taxonomy_code_2::TEXT,
    -- Deactivation status
    npi_deactivation_date::DATE,
    npi_reactivation_date::DATE,
    _source_year::INTEGER,
    _source_hash::TEXT,
    _source_file::TEXT,
    _loaded_at::TIMESTAMPTZ,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_nppes;
