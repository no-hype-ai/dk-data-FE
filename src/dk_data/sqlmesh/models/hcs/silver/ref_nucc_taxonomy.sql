-- SQLMesh Model: Silver NUCC Taxonomy Reference
-- Direct reference table from bronze NUCC taxonomy codes
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_silver.ref_nucc_taxonomy,
    kind FULL,
    cron '@daily',
    audits (
        not_null(columns := (taxonomy_code)),
        unique_values(columns := (taxonomy_code))
    ),
    grain (taxonomy_code)
);

SELECT
    gen_random_uuid()                           AS id,
    taxonomy_code,
    taxonomy_type                               AS type,
    classification,
    specialization,
    source,
    ingested_at,
    ingested_at                                 AS source_updated_at,
    NOW()                                       AS created_at
FROM hcs_bronze.cms_nucc;
