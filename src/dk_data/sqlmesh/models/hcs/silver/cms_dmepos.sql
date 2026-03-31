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

SELECT
    gen_random_uuid()               AS id,
    b.npi,
    b.hcpcs_code,
    b.total_services,
    b.total_beneficiaries,
    b.avg_submitted_charge,
    b.avg_medicare_payment,

    -- Provider identity from NPPES
    n.provider_name,
    n.provider_type,
    n.city,
    n.state,
    n.zip_code,

    b.source,
    b.source_updated_at,
    NOW()                           AS created_at

FROM hcs_bronze.cms_dmepos b
LEFT JOIN hcs_bronze.cms_nppes n ON b.npi = n.npi
WHERE b.npi IS NOT NULL
