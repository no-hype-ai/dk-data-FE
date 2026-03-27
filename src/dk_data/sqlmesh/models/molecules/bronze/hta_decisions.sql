-- SQLMesh Model: Bronze HTA Decisions
-- Transforms raw HTA agency decision flat-column records to Bronze typed columns
-- Part of: 015-assessment-dashboard-integration
--
-- Source table: raw.hta_decisions (flat columns, not JSONB response_body)
-- Loaded by: src/dk_data/ingestion/sources/hta_bodies.py
--
-- Field mapping from HTABodiesFetcher._normalize_nice_item:
--   decision_id   -> decision_id (prefixed "nice-{id}")
--   agency        -> agency      (nice | gba | has | pbac)
--   drug_name     -> drug_name   (item title or drug_name field)
--   indication    -> indication
--   decision_type -> decision_type
--   decision_date -> decision_date (YYYY-MM-DD)
--   document_url  -> document_url
--   summary       -> summary

MODEL (
    name bronze.hta_decisions,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key decision_id
    ),
    cron '@daily',
    audits (
        not_null(columns := (decision_id)),
        unique_values(columns := (decision_id))
    ),
    grain decision_id
);

SELECT
    gen_random_uuid()           AS id,

    -- Decision identifiers (decision_id stored directly by loader)
    r.decision_id::TEXT         AS decision_id,
    r.agency::TEXT              AS agency,
    r.drug_name::TEXT           AS drug_name,
    r.indication::TEXT          AS indication,
    r.decision_type::TEXT       AS decision_type,
    r.decision_date::DATE       AS decision_date,
    r.document_url::TEXT        AS document_url,
    r.summary::TEXT             AS summary,

    -- Source tracking
    'hta_decisions'             AS source,
    r._loaded_at                AS source_updated_at,
    FALSE                       AS processed_to_silver,
    NOW()                       AS created_at

FROM raw.hta_decisions r
WHERE
    r.drug_name IS NOT NULL
    AND r._loaded_at BETWEEN @start_dt AND @end_dt;
