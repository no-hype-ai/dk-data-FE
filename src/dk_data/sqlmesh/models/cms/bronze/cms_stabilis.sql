-- SQLMesh Model: Bronze CMS Stabilis IV Compatibility
-- Normalizes raw IV Drug Compatibility pairs to typed Bronze columns
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_stabilis,
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
    UPPER(TRIM(compatibility))                  AS compatibility,
    TRIM(solvent)                               AS solvent,
    TRIM(concentration)                         AS concentration,
    TRIM(reference)                             AS reference,
    _loaded_at,
    _source_file,
    _source_hash
FROM hcs_raw.cms_stabilis
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
