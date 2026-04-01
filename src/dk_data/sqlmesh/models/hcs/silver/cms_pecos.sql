-- SQLMesh Model: Silver CMS PECOS Provider Enrollment
-- Typed pass-through of CMS PECOS enrollment records from hcs_bronze.cms_pecos.
-- Links providers via NPI → hcs_bronze.cms_nppes for identity enrichment.
-- Consumers: provider_profile, enrollment validation, credentialing analysis.
-- Part of: issue #172 H3

MODEL (
    name hcs_silver.cms_pecos,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (enrollment_id))
    ),
    grain enrollment_id
);

SELECT DISTINCT ON (b.enrollment_id)
    gen_random_uuid()               AS id,
    b.enrollment_id,
    b.npi,
    b.organization_name,
    b.enrollment_type,
    b.enrollment_state,
    b.first_name,
    b.last_name,

    -- Provider identity from NPPES (most recent year via ORDER BY)
    -- entity_type_code: '1' = individual, '2' = organization
    COALESCE(n.provider_organization_name,
             n.provider_last_name || ', ' || n.provider_first_name) AS provider_name,
    n.entity_type_code                                              AS provider_type,
    n.provider_business_practice_location_address_city_name        AS provider_city,
    n.provider_business_practice_location_address_postal_code      AS provider_zip,

    b.source,
    b.ingested_at                   AS source_updated_at,
    NOW()                           AS created_at

FROM hcs_bronze.cms_pecos b
LEFT JOIN hcs_bronze.cms_nppes n ON b.npi = n.npi
WHERE b.enrollment_id IS NOT NULL
ORDER BY b.enrollment_id, n._source_year DESC NULLS LAST
