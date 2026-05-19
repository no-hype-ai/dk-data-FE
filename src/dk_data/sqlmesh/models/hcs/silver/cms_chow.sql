-- SQLMesh Model: Silver CMS Change of Ownership (CHOW)
-- Pure 1:1 passthrough of hcs_bronze.cms_chow. Cross-source enrichment columns
-- (cms_care_compare, cms_hospital_general_info) are no longer projected here per
-- the project rule that bronze column names are authoritative and aliases are
-- forbidden. Consumers needing facility context should join hcs_silver.cms_care_compare
-- or hcs_silver.cms_hospital_general_info on ccn = facility_id themselves.
-- Part of: issue #172 H3

MODEL (
    name hcs_silver.cms_chow,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (ccn, effective_date))
    ),
    grain (ccn, effective_date)
);

SELECT DISTINCT ON (b.ccn, b.effective_date)
    b.ccn,
    b.previous_owner,
    b.new_owner,
    b.effective_date,
    b.provider_type,

    b.source,
    b.ingested_at
FROM hcs_bronze.cms_chow b
WHERE b.ccn IS NOT NULL
  AND b.effective_date IS NOT NULL
ORDER BY b.ccn, b.effective_date, b.ingested_at DESC NULLS LAST
