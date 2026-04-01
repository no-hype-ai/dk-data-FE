-- SQLMesh Model: Bronze CMS DDInter Drug Interactions
-- Extracts typed columns from JSONB response_body
-- Part of: 016-cms-puf-datasource-integration
--
-- ⚠️ RETIRED (020-drugbank-seed-schema-fix): The DDInter source (ddinter.scbdd.com)
-- has been permanently unreachable since March 2026. This model has no downstream
-- silver or gold consumers. Drug-drug interaction data is fully covered by
-- mol_bronze.drugbank (drug_interactions column) → mol_silver.drug_pharmacology.
-- The fetcher, CronJob, and sources/__init__.py entry have been removed.
-- This model is retained to keep hcs_raw.cms_ddinter readable if historical
-- raw data was ingested before the outage.

MODEL (
    name hcs_bronze.cms_ddinter,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        batch_size 500
    ),
    cron '@yearly',  -- retired source; run at most once yearly to avoid scheduler noise
    audits (not_null(columns := (drug_a, drug_b))),
    grain (drug_a, drug_b)
);

SELECT
    response_body->>'drug_a'            AS drug_a,
    response_body->>'drug_b'            AS drug_b,
    response_body->>'interaction_type'  AS interaction_type,
    response_body->>'severity'          AS severity,
    response_body->>'description'       AS description,
    response_body                       AS raw_json,
    id                                  AS raw_source_id,
    'cms_ddinter'                       AS source,
    FALSE AS processed_to_silver,
    ingested_at
FROM hcs_raw.cms_ddinter
WHERE response_status = 200
  AND ingested_at BETWEEN @start_dt AND @end_dt;
