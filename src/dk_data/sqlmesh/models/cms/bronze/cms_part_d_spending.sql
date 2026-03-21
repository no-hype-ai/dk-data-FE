-- SQLMesh Model: Bronze CMS Part D Spending by Drug
-- Normalizes raw Part D Drug Spending Dashboard to typed Bronze columns
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name bronze.cms_part_d_spending,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (brand_name, year))),
    grain (brand_name, year)
);

SELECT
    UPPER(TRIM(brand_name))                     AS brand_name,
    UPPER(TRIM(generic_name))                   AS generic_name,
    COALESCE(total_spending, 0)::NUMERIC(14,2)  AS total_spending,
    COALESCE(total_claims, 0)::INTEGER          AS total_claims,
    COALESCE(total_beneficiaries, 0)::INTEGER   AS total_beneficiaries,
    COALESCE(avg_cost_per_claim, 0)::NUMERIC(10,2) AS avg_cost_per_claim,
    year::INTEGER                               AS year,
    _loaded_at,
    _source_file,
    _source_hash
FROM hcs_raw.cms_part_d_spending
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
