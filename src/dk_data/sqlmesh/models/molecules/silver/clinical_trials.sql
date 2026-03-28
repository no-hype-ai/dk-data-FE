-- SQLMesh Model: Silver Clinical Trials
-- Transforms Bronze ClinicalTrials.gov data to normalized Silver layer
-- Part of: 012-dk-data-platform
-- Updated: 019-cms-puf-platform-reconciliation — zero column loss audit pass
--   All bronze columns now promoted; eligibility, locations, results, and oversight
--   columns were previously dropped without justification.

MODEL (
    name mol_silver.clinical_trials,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column source_updated_at,
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

    -- External Identifiers
    b.nct_id,
    b.org_study_id,
    b.acronym,

    -- Titles
    b.brief_title AS title,
    b.official_title,

    -- Summary
    b.brief_summary,
    b.detailed_description,

    -- Status
    b.overall_status,
    b.last_known_status,
    b.why_stopped,

    -- Phase (derived string + original JSONB array)
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
    b.phases AS phases_raw,

    -- Dates
    b.start_date,
    b.completion_date,
    b.completion_date AS end_date,
    b.primary_completion_date,
    b.first_submit_date,
    b.first_post_date,
    b.last_update_date,

    -- Conditions and Keywords
    b.conditions,
    b.keywords,

    -- Interventions and Arms
    b.interventions,
    b.arm_groups,

    -- Study Design
    b.study_type,
    b.allocation,
    b.intervention_model,
    b.masking,
    b.enrollment_count AS enrollment,
    b.enrollment_type,

    -- Eligibility (previously dropped — restored in 019)
    b.eligibility_sex,
    b.minimum_age,
    b.maximum_age,
    b.healthy_volunteers,
    b.eligibility_criteria,

    -- Sponsors
    b.lead_sponsor_name AS lead_sponsor,
    b.lead_sponsor_class,
    b.collaborators,
    b.responsible_party,

    -- Contacts and Locations (previously dropped — restored in 019)
    b.central_contacts,
    b.locations,

    -- Outcomes
    b.primary_outcomes,
    b.secondary_outcomes,

    -- Results (previously dropped — restored in 019)
    b.has_results,
    b.results_section,

    -- Oversight (extracted directly from raw_json — not in typed bronze columns)
    (b.raw_json->'protocolSection'->'oversightModule'->>'isFdaRegulatedDrug')::BOOLEAN AS fda_regulated_drug,
    (b.raw_json->'protocolSection'->'oversightModule'->>'isFdaRegulatedDevice')::BOOLEAN AS fda_regulated_device,
    (b.raw_json->'protocolSection'->'oversightModule'->>'humanSubjectReviewBoard' = 'Yes')::BOOLEAN AS has_dmc,

    -- Entity resolution: derive molecule_id by matching DRUG intervention names to mol_silver.molecules
    (
        SELECT m.molecule_id
        FROM jsonb_array_elements(COALESCE(b.interventions, '[]'::jsonb)) AS interv
        JOIN mol_silver.molecules m
            ON interv->>'type' = 'DRUG'
           AND LOWER(m.canonical_name) = LOWER(interv->>'name')
        LIMIT 1
    ) AS molecule_id,

    -- Source Tracking
    b.id AS bronze_id,
    'clinicaltrials_gov' AS source,
    b.request_timestamp AS source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at

FROM mol_bronze.clinicaltrials b
WHERE
    b.processed_to_silver = FALSE
    AND b.nct_id IS NOT NULL
    AND b.request_timestamp BETWEEN @start_dt AND @end_dt;
