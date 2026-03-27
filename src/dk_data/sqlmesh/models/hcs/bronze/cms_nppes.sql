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
    -- Individual name fields
    provider_last_name::TEXT,
    provider_first_name::TEXT,
    provider_middle_name::TEXT,
    provider_credential_text::TEXT,
    -- Organization name
    provider_organization_name::TEXT,
    -- Mailing address (used by idn_hierarchy agent)
    provider_first_line_business_mailing_address::TEXT,
    provider_second_line_business_mailing_address::TEXT,
    provider_business_mailing_address_city_name::TEXT,
    provider_business_mailing_address_state_name::TEXT,
    provider_business_mailing_address_postal_code::TEXT,
    provider_business_mailing_address_telephone_number::TEXT,
    -- Practice location (used by contact_verification and silver provider_profile)
    provider_first_line_business_practice_location_address::TEXT,
    provider_business_practice_location_address_city_name::TEXT,
    provider_business_practice_location_address_state_name::TEXT,
    provider_business_practice_location_address_postal_code::TEXT,
    provider_business_practice_location_address_telephone_number::TEXT,
    provider_business_practice_location_address_fax_number::TEXT,
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
