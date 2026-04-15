-- SQLMesh Model: Bronze FDA Form 483 Observations
-- Passthrough from mol_raw.fda_483_observations to typed bronze layer.
-- Feature: 006-claims-engine-data-gaps (T074)

MODEL (
    name mol_bronze.fda_483_observations,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key observation_id
    ),
    cron '@daily',
    audits (
        not_null(columns := (observation_id))
    ),
    grain (observation_id)
);

SELECT
    r.observation_id::TEXT              AS observation_id,
    r.inspection_date                   AS inspection_date,
    r.company_name::TEXT                AS company_name,
    r.facility::TEXT                    AS facility,
    r.observations::JSONB               AS observations,
    r.full_text::TEXT                   AS full_text,
    r.drug_mentions::JSONB              AS drug_mentions,

    -- Source tracking
    'fda_483_observations'              AS source,
    r.ingested_at                       AS source_updated_at,
    FALSE                               AS processed_to_silver,
    r.ingested_at                       AS ingested_at

FROM mol_raw.fda_483_observations r
WHERE r.observation_id IS NOT NULL
  AND r.ingested_at BETWEEN @start_dt AND @end_dt;
