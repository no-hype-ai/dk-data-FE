-- SQLMesh Model: Bronze CMS Stabilis IV Compatibility
-- Normalizes raw IV Drug Stability/Compatibility reference to typed Bronze columns
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name bronze.cms_stabilis,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (drug_name, route))),
    grain (drug_name, route)
);

SELECT
    UPPER(TRIM(drug_name))                      AS drug_name,
    UPPER(TRIM(route))                          AS route,
    UPPER(TRIM(diluent))                        AS diluent,
    COALESCE(stability_hours, 0)::NUMERIC(6,1)  AS stability_hours,
    UPPER(TRIM(storage_condition))              AS storage_condition,
    _loaded_at,
    _source_file,
    _source_hash
FROM raw.cms_stabilis
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
