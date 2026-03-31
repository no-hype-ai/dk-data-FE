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

SELECT
    gen_random_uuid()               AS id,
    b.enrollment_id,
    b.npi,
    b.organization_name,
    b.enrollment_type,
    b.enrollment_state,
    b.first_name,
    b.last_name,

    -- Provider identity from NPPES
    n.provider_name,
    n.provider_type,
    n.city                          AS provider_city,
    n.zip_code                      AS provider_zip,

    b.source,
    b.source_updated_at,
    NOW()                           AS created_at

FROM hcs_bronze.cms_pecos b
LEFT JOIN hcs_bronze.cms_nppes n ON b.npi = n.npi
WHERE b.enrollment_id IS NOT NULL
