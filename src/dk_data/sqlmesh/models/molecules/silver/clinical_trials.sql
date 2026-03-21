-- SQLMesh Model: Silver Clinical Trials
-- Zero data loss from Bronze. Column names match bronze (API-derived snake_case).
-- Adds: molecule_id linkage.

MODEL (
    name mol_silver.clinical_trials,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key nct_id
    ),
    cron '@daily',
    audits (
        not_null(columns := (nct_id)),
        unique_values(columns := (nct_id))
    ),
    grain nct_id
);

SELECT
    gen_random_uuid() AS trial_id,

    -- All bronze columns carried forward with SAME NAMES (API-derived)
    b.nct_id,
    b.org_study_id,
    b.brief_title,
    b.official_title,
    b.acronym,
    b.brief_summary,
    b.detailed_description,
    b.overall_status,
    b.last_known_status,
    b.why_stopped,
    b.phase,
    b.phases,
    b.start_date,
    b.start_date_type,
    b.completion_date,
    b.completion_date_type,
    b.primary_completion_date,
    b.study_first_submit_date,
    b.study_first_post_date,
    b.last_update_post_date,
    b.study_type,
    b.allocation,
    b.intervention_model,
    b.primary_purpose,
    b.masking,
    b.enrollment_count,
    b.enrollment_type,
    b.conditions,
    b.keywords,
    b.mesh_terms,
    b.interventions,
    b.arms_groups,
    b.eligibility_criteria,
    b.sex,
    b.minimum_age,
    b.maximum_age,
    b.healthy_volunteers,
    b.lead_sponsor_name,
    b.lead_sponsor_class,
    b.collaborators,
    b.central_contacts,
    b.locations,
    b.primary_outcomes,
    b.secondary_outcomes,
    b.fda_regulated_drug,
    b.fda_regulated_device,
    b.ipd_sharing,
    b.has_results,
    b.results_section,
    b.results_participant_flow,
    b.results_baseline,
    b.results_outcome_measures,
    b.results_adverse_events,
    b.condition_browse,
    b.intervention_browse,
    b.references,

    -- Source tracking
    b.id AS bronze_id,
    b.ingested_at,
    NOW() AS created_at,
    NOW() AS updated_at

FROM mol_bronze.clinicaltrials b
WHERE
    b.processed_to_silver = FALSE
    AND b.nct_id IS NOT NULL;
