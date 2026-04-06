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
    grain (npi, facility_affiliations_certification_number)
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
    n.entity_type_code                                              AS provider_type,
    n.provider_business_practice_location_address_state_name       AS provider_state,

    -- Facility identity from hospital general info (most recent year via ORDER BY)
    h.facility_name,
    h.city_town                     AS facility_city,
    h.state                         AS facility_state,

    b.source,
    b.ingested_at                   AS source_updated_at,
    NOW()                           AS created_at

FROM hcs_bronze.cms_hospital_affiliation b
LEFT JOIN hcs_bronze.cms_nppes n
       ON b.npi = n.npi
LEFT JOIN hcs_bronze.cms_hospital_general_info h
       ON b.facility_affiliations_certification_number = h.facility_id
WHERE b.npi IS NOT NULL
ORDER BY b.npi, b.facility_affiliations_certification_number, n._source_year DESC NULLS LAST, h._source_year DESC NULLS LAST
