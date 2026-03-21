-- SQLMesh Model: Gold Trial Outcomes
-- Combined trial outcomes from clinical trials registry and publication evidence
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name mol_gold.trial_outcomes,
    kind FULL,
    cron '@weekly',
    audits (
        not_null(columns := (evidence_source, confidence_score))
    ),
    grain (molecule_id, trial_nct_id, evidence_source)
);

-- Source 1: ClinicalTrials.gov structured results data
WITH registry_outcomes AS (
    SELECT
        ct.molecule_id,
        ct.nct_id AS trial_nct_id,
        'clinicaltrials_gov' AS evidence_source,
        po->>'measure' AS endpoint_name,
        NULL::NUMERIC AS hazard_ratio,
        NULL::NUMERIC AS p_value,
        NULL::NUMERIC AS response_rate,
        ct.enrollment AS sample_size,
        1.0::NUMERIC AS confidence_score,
        ct.start_date AS evidence_date
    FROM mol_silver.clinical_trials ct,
        jsonb_array_elements(ct.primary_outcomes) AS po
    WHERE ct.has_results = TRUE
      AND ct.molecule_id IS NOT NULL
),

-- Source 2: Publication-extracted evidence (LLM-extracted, confidence >= 0.40)
publication_outcomes AS (
    SELECT
        pe.molecule_id,
        pe.trial_nct_id,
        'publication' AS evidence_source,
        pe.endpoint_name,
        pe.hazard_ratio,
        pe.p_value,
        pe.response_rate,
        pe.sample_size,
        pe.confidence_score,
        pe.created_at::DATE AS evidence_date
    FROM xenon.publication_evidence pe
    WHERE pe.confidence_score >= 0.40
      AND pe.molecule_id IS NOT NULL
)

SELECT
    gen_random_uuid() AS id,
    molecule_id,
    trial_nct_id,
    evidence_source,
    endpoint_name,
    hazard_ratio,
    p_value,
    response_rate,
    sample_size,
    confidence_score,
    evidence_date,
    NOW() AS created_at,
    NOW() AS updated_at
FROM registry_outcomes
UNION ALL
SELECT
    gen_random_uuid() AS id,
    molecule_id,
    trial_nct_id,
    evidence_source,
    endpoint_name,
    hazard_ratio,
    p_value,
    response_rate,
    sample_size,
    confidence_score,
    evidence_date,
    NOW() AS created_at,
    NOW() AS updated_at
FROM publication_outcomes;
