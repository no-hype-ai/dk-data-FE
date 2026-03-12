-- SQLMesh Model: Silver NUCC Taxonomy Reference
-- Direct reference table from bronze NUCC taxonomy codes
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name silver.ref_nucc_taxonomy,
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
    provider_type                               AS type,
    classification,
    specialization,
    grouping_name                               AS grouping
FROM bronze.cms_nucc;
