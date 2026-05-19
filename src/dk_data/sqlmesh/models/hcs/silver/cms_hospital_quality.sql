-- SQLMesh Model: Silver CMS Hospital Quality Ratings
-- Pure 1:1 passthrough of hcs_bronze.cms_hospital_quality. Cross-source enrichment
-- (cms_care_compare) is no longer projected here per the project rule that bronze
-- column names are authoritative and aliases are forbidden. Consumers needing the
-- joined facility master should join hcs_silver.cms_care_compare on facility_id.
-- Part of: issue #172 H3

MODEL (
    name hcs_silver.cms_hospital_quality,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (facility_id))
    ),
    grain facility_id
);

SELECT DISTINCT ON (b.facility_id)
    b.facility_id,
    b.facility_name,
    b.overall_rating,
    b.mortality_rating,
    b.safety_rating,
    b.readmission_rating,
    b.patient_experience_rating,
    b.timeliness_rating,

    b.source,
    b.ingested_at
FROM hcs_bronze.cms_hospital_quality b
WHERE b.facility_id IS NOT NULL
ORDER BY b.facility_id, b.ingested_at DESC
