-- SQLMesh Model: Bronze FDA Complete Response Letters (CRLs)
-- Passthrough from mol_raw.fda_crls to typed bronze layer.
-- Feature: 006-claims-engine-data-gaps (T074)

MODEL (
    name mol_bronze.fda_crls,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key crl_id
    ),
    cron '@daily',
    audits (
        not_null(columns := (crl_id))
    ),
    grain (crl_id)
);

SELECT
    r.crl_id::TEXT                      AS crl_id,
    r.crl_date                          AS crl_date,
    r.company_name::TEXT                AS company_name,
    r.drug_name::TEXT                   AS drug_name,
    r.application_number::TEXT          AS application_number,
    r.reason::TEXT                      AS reason,
    r.full_text::TEXT                   AS full_text,
    r.drug_mentions::JSONB              AS drug_mentions,

    -- Source tracking
    'fda_crls'                          AS source,
    r.ingested_at                       AS source_updated_at,
    FALSE                               AS processed_to_silver,
    r.ingested_at                       AS ingested_at

FROM mol_raw.fda_crls r
WHERE r.crl_id IS NOT NULL
  AND r.ingested_at BETWEEN @start_dt AND @end_dt;
