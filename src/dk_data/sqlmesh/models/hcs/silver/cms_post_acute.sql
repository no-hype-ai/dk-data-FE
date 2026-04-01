-- SQLMesh Model: Silver CMS Post-Acute Care Facilities
-- Performance metrics for SNF, HHA, IRF, and LTCH facilities.
-- Grain: (ccn, year)
-- Linkage: CCN → hcs_bronze.cms_hospital_general_info (most recent year via DISTINCT ON)

MODEL (
    name hcs_silver.cms_post_acute,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (ccn))
    ),
    grain (ccn, year)
);

SELECT DISTINCT ON (b.ccn, b.year)
    gen_random_uuid()           AS id,
    b.ccn,
    b.provider_name,
    b.provider_type,
    b.total_episodes,
    b.avg_episode_payment,
    b.readmission_rate,
    b.year,

    -- Facility enrichment from hospital general info (most recent year)
    h.facility_name             AS hgi_facility_name,
    h.city_town                 AS facility_city,
    h.state                     AS facility_state,
    h.hospital_type,

    b.source,
    b.ingested_at               AS source_updated_at,
    NOW()                       AS created_at

FROM hcs_bronze.cms_post_acute b
LEFT JOIN hcs_bronze.cms_hospital_general_info h
       ON b.ccn = h.facility_id

WHERE b.ccn IS NOT NULL
ORDER BY b.ccn, b.year, h._source_year DESC NULLS LAST
