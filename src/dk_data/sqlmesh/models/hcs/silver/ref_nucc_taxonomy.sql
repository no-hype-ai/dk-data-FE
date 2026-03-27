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
    taxonomy_code,
    taxonomy_type                               AS type,
    classification,
    specialization
FROM hcs_bronze.cms_nucc;
