-- SQLMesh Model: mol_silver.publication_evidence
-- Promotes records from mol_silver.publication_evidence_staging to the live table.
-- Agent writes to staging; this model merges staging -> live.
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name mol_silver.publication_evidence,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key content_hash
    ),
    cron '@daily',
    grain content_hash
);

SELECT
    id,
    content_hash,
    molecule_id,
    trial_nct_id,
    pmid,
    doi,
    endpoint_name,
    endpoint_type,
    hazard_ratio,
    p_value,
    response_rate,
    median_survival_months,
    sample_size,
    confidence_score,
    needs_review,
    evidence_date,
    source_model,
    staged_at AS created_at,
    NOW() AS updated_at
FROM mol_silver.publication_evidence_staging
WHERE promoted_at IS NULL
  AND confidence_score >= 0.40;
