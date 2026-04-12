-- SQLMesh Model: Silver CMS Provider of Services (POS)
-- Pure 1:1 passthrough of hcs_bronze.cms_pos. Cross-source enrichment columns
-- (cms_care_compare, cms_hospital_general_info) are no longer projected here per
-- the project rule that bronze column names are authoritative and aliases are
-- forbidden. Consumers needing the joined denormalized view should join the
-- relevant silver passthroughs (hcs_silver.cms_care_compare,
-- hcs_silver.cms_hospital_general_info) themselves, or use hcs_silver.cms_facility_profile
-- which retains the multi-source aggregation under the gold-style exception.
-- Part of: issue #172 H3

MODEL (
    name hcs_silver.cms_pos,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (ccn))
    ),
    grain ccn,
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

SELECT DISTINCT ON (b.ccn)
    b.ccn,
    b.facility_name,
    b.street_address,
    b.city,
    b.state,
    b.zip_code,
    b.provider_type,
    b.beds,
    b.ownership_type,

    b.source,
    b.ingested_at
FROM hcs_bronze.cms_pos b
WHERE b.ccn IS NOT NULL
ORDER BY b.ccn, b.ingested_at DESC NULLS LAST
