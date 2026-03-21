-- SQLMesh Model: Bronze CMS Geographic Variation
-- Normalizes raw Geographic Variation PUF to typed Bronze columns
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name bronze.cms_geographic_variation,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (state, county))),
    grain (state, county)
);

SELECT
    UPPER(TRIM(state))                          AS state,
    UPPER(TRIM(county))                         AS county,
    COALESCE(bene_count, 0)::INTEGER            AS bene_count,
    COALESCE(total_actual_costs, 0)::NUMERIC(14,2) AS total_actual_costs,
    COALESCE(per_capita_costs, 0)::NUMERIC(10,2) AS per_capita_costs,
    year::INTEGER                               AS year,
    _loaded_at,
    _source_file,
    _source_hash
FROM hcs_raw.cms_geographic_variation
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
