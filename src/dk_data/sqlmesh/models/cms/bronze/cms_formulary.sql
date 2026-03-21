-- SQLMesh Model: Bronze CMS Medicare Formulary
-- Normalizes raw Medicare Part D Formulary data to typed Bronze columns
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name bronze.cms_formulary,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (rxcui))),
    grain (contract_id, plan_id, rxcui)
);

SELECT
    TRIM(contract_id)::TEXT                     AS contract_id,
    TRIM(plan_id)::TEXT                         AS plan_id,
    TRIM(formulary_id)::TEXT                    AS formulary_id,
    TRIM(rxcui)::TEXT                           AS rxcui,
    TRIM(drug_name)::TEXT                       AS drug_name,
    TRIM(tier_level)::TEXT                      AS tier_level,
    TRIM(prior_auth)::TEXT                      AS prior_auth,
    TRIM(step_therapy)::TEXT                    AS step_therapy,
    TRIM(quantity_limit)::TEXT                   AS quantity_limit,
    _loaded_at,
    _source_file,
    _source_hash
FROM hcs_raw.cms_formulary
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
