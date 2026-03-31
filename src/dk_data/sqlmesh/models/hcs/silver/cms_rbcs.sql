-- SQLMesh Model: Silver CMS RBCS Classification
-- Typed pass-through of CMS Restructured BETOS Classification System records
-- from hcs_bronze.cms_rbcs. Pure reference table mapping HCPCS codes to
-- RBCS categories; no mol or facility linkage applicable.
-- Consumers: provider utilization analytics, procedure classification, spend analysis.
-- Part of: issue #172 H3

MODEL (
    name hcs_silver.cms_rbcs,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (hcpcs_code))
    ),
    grain hcpcs_code
);

SELECT
    gen_random_uuid()               AS id,
    b.hcpcs_code,
    b.rbcs_id,
    b.rbcs_category,
    b.rbcs_subcategory,
    b.rbcs_family,

    b.source,
    b.source_updated_at,
    NOW()                           AS created_at

FROM hcs_bronze.cms_rbcs b
WHERE b.hcpcs_code IS NOT NULL
