-- SQLMesh Model: Bronze CMS DDInter Drug Interactions
-- Normalizes raw Drug-Drug Interactions reference to typed Bronze columns
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name bronze.cms_ddinter,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (drug_a, drug_b))),
    grain (drug_a, drug_b)
);

SELECT
    UPPER(TRIM(drug_a))                         AS drug_a,
    UPPER(TRIM(drug_b))                         AS drug_b,
    UPPER(TRIM(interaction_type))               AS interaction_type,
    UPPER(TRIM(severity))                       AS severity,
    TRIM(description)                           AS description,
    _loaded_at,
    _source_file,
    _source_hash
FROM hcs_raw.cms_ddinter
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
