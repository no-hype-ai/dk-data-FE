-- SQLMesh Model: Silver CMS DMEPOS Supplier Directory
-- Typed pass-through of Durable Medical Equipment, Prosthetics, Orthotics and Supplies
-- supplier data from hcs_bronze.cms_dmepos. Links providers via NPI.
-- Consumers: provider_profile, facility analytics.
-- Part of: issue #172 H3

MODEL (
    name hcs_silver.cms_dmepos,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (npi, source))
    ),
    grain npi
);

SELECT DISTINCT ON (b.npi)
    gen_random_uuid()               AS id,
    b.npi,
    b.hcpcs_code,
    b.total_services,
    b.total_beneficiaries,
    b.avg_submitted_charge,
    b.avg_medicare_payment,

    -- Provider identity from NPPES (most recent year via ORDER BY)
    -- entity_type_code: '1' = individual, '2' = organization
    COALESCE(n.provider_organization_name,
             n.provider_last_name || ', ' || n.provider_first_name) AS provider_name,
    n.entity_type_code                                              AS provider_type,
    n.provider_business_practice_location_address_city_name        AS city,
    n.provider_business_practice_location_address_state_name       AS state,
    n.provider_business_practice_location_address_postal_code      AS zip_code,

    b.source,
    b.ingested_at                   AS source_updated_at,
    NOW()                           AS created_at

FROM hcs_bronze.cms_dmepos b
LEFT JOIN hcs_bronze.cms_nppes n ON b.npi = n.npi
WHERE b.npi IS NOT NULL
ORDER BY b.npi, n._source_year DESC NULLS LAST
