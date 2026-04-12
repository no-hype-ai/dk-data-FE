-- SQLMesh Model: Gold Trial Outcomes
-- Combined trial outcomes from clinical trials registry and publication evidence
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name mol_gold.trial_outcomes,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (molecule_id, trial_nct_id, endpoint_name, evidence_source)
    ),
    cron '@weekly',
    audits (
        not_null(columns := (evidence_source, confidence_score))
    ),
    grain (molecule_id, trial_nct_id, endpoint_name, evidence_source),
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

-- Source 1: ClinicalTrials.gov structured results data
-- molecule_id is resolved by joining intervention drug names to mol_silver.molecule_names
WITH trial_molecule_links AS (
    SELECT DISTINCT
        ct.nct_id,
        ma.molecule_id
    FROM mol_silver.clinical_trials ct
    CROSS JOIN LATERAL jsonb_array_elements(ct.interventions) AS iv
    JOIN mol_silver.molecule_names ma
      ON LOWER(iv->>'name') = LOWER(ma.display_name)
    WHERE ct.interventions IS NOT NULL
),

registry_outcomes AS (
    SELECT
        tml.molecule_id,
        ct.nct_id AS trial_nct_id,
        'clinicaltrials_gov' AS evidence_source,
        po->>'measure' AS endpoint_name,
        NULL::NUMERIC AS hazard_ratio,
        NULL::NUMERIC AS p_value,
        NULL::NUMERIC AS response_rate,
        ct.enrollment_count AS sample_size,
        1.0::NUMERIC AS confidence_score,
        ct.start_date AS evidence_date
    FROM mol_silver.clinical_trials ct
    JOIN trial_molecule_links tml ON tml.nct_id = ct.nct_id
    CROSS JOIN LATERAL jsonb_array_elements(ct.primary_outcomes) AS po
    WHERE ct.has_results = TRUE
      AND ct.primary_outcomes IS NOT NULL
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
    FROM mol_silver.publication_evidence pe
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
