-- SQLMesh Model: Silver Clinical Trials
-- Transforms Bronze ClinicalTrials.gov data to normalized Silver layer
-- Part of: 012-dk-data-platform

MODEL (
    name silver.clinical_trials,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        batch_size 1000
    ),
    cron '@daily',
    audits (
        not_null(columns := (nct_id, title)),
        unique_values(columns := (nct_id))
    ),
    grain nct_id
);

SELECT
    gen_random_uuid() AS trial_id,

    -- External Identifiers (read typed columns directly from bronze — not raw JSON)
    b.nct_id,
    b.org_study_id,

    -- Title
    b.brief_title AS title,
    b.official_title,

    -- Summary (typed TEXT columns in bronze)
    b.brief_summary,
    b.detailed_description,

    -- Phase (derived from the typed phases JSONB array using ::TEXT for LIKE matching)
    CASE
        WHEN b.phases::TEXT LIKE '%PHASE1%' AND b.phases::TEXT LIKE '%PHASE2%' THEN 'Phase 1/2'
        WHEN b.phases::TEXT LIKE '%PHASE2%' AND b.phases::TEXT LIKE '%PHASE3%' THEN 'Phase 2/3'
        WHEN b.phases::TEXT LIKE '%PHASE1%' THEN 'Phase 1'
        WHEN b.phases::TEXT LIKE '%PHASE2%' THEN 'Phase 2'
        WHEN b.phases::TEXT LIKE '%PHASE3%' THEN 'Phase 3'
        WHEN b.phases::TEXT LIKE '%PHASE4%' THEN 'Phase 4'
        WHEN b.phases::TEXT LIKE '%EARLY%' THEN 'Early Phase 1'
        ELSE 'Not Applicable'
    END AS phase,

    b.overall_status,

    -- Dates (already typed DATE in bronze)
    b.start_date,
    b.completion_date,
    b.completion_date AS end_date,
    -- primary_completion_date is a separate column in the bronze model
    b.primary_completion_date,

    -- Conditions (already typed JSONB in bronze)
    b.conditions,

    -- Interventions (already typed JSONB in bronze)
    b.interventions,

    -- Study Design (already typed in bronze)
    b.study_type,
    b.allocation,
    b.intervention_model,
    b.masking,
    b.enrollment_count AS enrollment,

    -- Sponsors (already typed in bronze)
    b.lead_sponsor_name AS lead_sponsor,
    b.collaborators,

    -- Outcomes (already typed JSONB in bronze)
    b.primary_outcomes,
    b.secondary_outcomes,

    -- Results (has_results is a typed BOOLEAN column in the bronze model)
    b.has_results,

    -- Source Tracking
    b.id AS bronze_id,
    'clinicaltrials_gov' AS source,
    b.ingested_at,
    b.ingested_at AS source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at

FROM bronze.clinicaltrials b
WHERE
    b.processed_to_silver = FALSE
    AND b.nct_id IS NOT NULL
    AND b.ingested_at BETWEEN @start_dt AND @end_dt;
