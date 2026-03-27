-- SQLMesh Model: Gold Trial Outcomes
-- Combined trial outcomes from clinical trials registry and publication evidence
-- Part of: 015-assessment-dashboard-integration
-- Updated: 019-cms-puf-platform-reconciliation — removed xenon.publication_evidence reference,
--          replaced with mol_silver.publication_evidence; extended grain with endpoint_name.
--
-- GRAIN CHANGE NOTE: adding endpoint_name produces more rows per (molecule_id, trial_nct_id)
-- than the prior grain. api/routes/data_platform.py callers that aggregate per-trial must
-- GROUP BY endpoint_name or use aggregation functions if they expect one row per trial.

MODEL (
    name mol_gold.trial_outcomes,
    kind FULL,
    cron '@weekly',
    audits (
        not_null(columns := (evidence_source, confidence_score))
    ),
    grain (molecule_id, trial_nct_id, endpoint_name, evidence_source)
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
    FROM silver.clinical_trials ct,
        jsonb_array_elements(ct.primary_outcomes) AS po
    WHERE ct.has_results = TRUE
      AND ct.molecule_id IS NOT NULL
),

-- Source 2: Publication-extracted evidence (LLM-extracted from mol_silver.publication_evidence)
-- Replaces prior reference to xenon.publication_evidence (feature 019-cms-puf-platform-reconciliation)
-- Filters: confidence >= 0.40 AND needs_review = FALSE (only reviewed/promoted records)
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
    FROM mol_silver.publication_evidence pe
    WHERE pe.confidence_score >= 0.40
      AND pe.needs_review = FALSE
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
