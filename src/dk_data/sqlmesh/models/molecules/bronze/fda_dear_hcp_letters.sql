-- SQLMesh Model: Bronze FDA Dear Healthcare Professional Letters
-- Passthrough from mol_raw.fda_dear_hcp_letters to typed bronze layer.
-- Feature: 006-claims-engine-data-gaps (T074)

MODEL (
    name mol_bronze.fda_dear_hcp_letters,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key letter_id
    ),
    cron '@daily',
    audits (
        not_null(columns := (letter_id))
    ),
    grain (letter_id)
);

SELECT
    r.letter_id::TEXT                   AS letter_id,
    r.letter_date                       AS letter_date,
    r.company_name::TEXT                AS company_name,
    r.subject::TEXT                     AS subject,
    r.drug_name::TEXT                   AS drug_name,
    r.full_text::TEXT                   AS full_text,
    r.drug_mentions::JSONB              AS drug_mentions,

    -- Source tracking
    'fda_dear_hcp_letters'              AS source,
    r.ingested_at                       AS source_updated_at,
    FALSE                               AS processed_to_silver,
    r.ingested_at                       AS ingested_at

FROM mol_raw.fda_dear_hcp_letters r
WHERE r.letter_id IS NOT NULL
  AND r.ingested_at BETWEEN @start_dt AND @end_dt;
