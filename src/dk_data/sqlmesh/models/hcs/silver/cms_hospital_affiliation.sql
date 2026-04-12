-- SQLMesh Model: Silver CMS Hospital Affiliation
-- Provider-to-facility affiliation records from hcs_bronze.cms_hospital_affiliation.
-- Links providers via NPI → hcs_bronze.cms_nppes and facilities via
-- certification number → hcs_bronze.cms_hospital_general_info.
-- Consumers: provider_profile, facility_profile, referral network analysis.
-- Part of: issue #172 H3

MODEL (
    name hcs_silver.cms_hospital_affiliation,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (npi))
    ),
    grain (npi, facility_affiliations_certification_number),
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

SELECT DISTINCT ON (b.npi, b.facility_affiliations_certification_number)
    gen_random_uuid()               AS id,
    b.npi,
    b.ind_pac_id,
    b.provider_last_name,
    b.provider_first_name,
    b.provider_middle_name,
    b.facility_type,
    b.facility_affiliations_certification_number,
    b.facility_type_certification_number,

    -- Provider identity from NPPES (most recent year via ORDER BY)
    -- entity_type_code: '1' = individual, '2' = organization
    COALESCE(n.provider_organization_name,
             n.provider_last_name || ', ' || n.provider_first_name) AS provider_name,
    n.entity_type_code,
    n.provider_credential_text,
    n.provider_business_practice_location_address_city_name,
    n.provider_business_practice_location_address_state_name,
    n.provider_business_practice_location_address_postal_code,
    n.provider_business_practice_location_address_telephone_number,
    n.healthcare_provider_taxonomy_code_1,
    n.healthcare_provider_taxonomy_code_2,
    n.npi_deactivation_date,
    n.npi_reactivation_date,

    -- Facility identity from hospital general info (most recent year via ORDER BY)
    h.facility_name,
    h.address,
    h.city_town,
    h.state,
    h.zip_code,
    h.county_parish,
    h.telephone_number,
    h.hospital_type,
    h.hospital_ownership,
    h.emergency_services,
    h.meets_criteria_for_birthing_friendly_designation,
    h.hospital_overall_rating,
    h.hospital_overall_rating_footnote,

    b.source,
    b.ingested_at,
    NOW()                           AS created_at

FROM hcs_bronze.cms_hospital_affiliation b
LEFT JOIN hcs_bronze.cms_nppes n
       ON b.npi = n.npi
LEFT JOIN hcs_bronze.cms_hospital_general_info h
       ON b.facility_affiliations_certification_number = h.facility_id
WHERE b.npi IS NOT NULL
ORDER BY b.npi, b.facility_affiliations_certification_number, n._source_year DESC NULLS LAST, h._source_year DESC NULLS LAST
