-- SQLMesh Model: Silver Clinical Trials
-- Zero data loss from Bronze. Column names match bronze (API-derived snake_case).
-- Entity linking: LEFT JOIN to mol_silver.molecules by canonical_name fuzzy match.
-- FULL refresh ensures molecule_id is always current when new molecules are added.

MODEL (
    name mol_silver.clinical_trials,
    kind FULL,
    cron '@daily',
    audits (
        not_null(columns := (nct_id)),
        unique_values(columns := (nct_id))
    ),
    grain nct_id
);

SELECT
    gen_random_uuid() AS trial_id,

    -- All bronze columns carried forward (names match actual bronze/API schema)
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
    b.phases,
    b.start_date,
    b.completion_date,
    b.primary_completion_date,
    b.first_submit_date,
    b.first_post_date,
    b.last_update_date,
    b.study_type,
    b.allocation,
    b.intervention_model,
    b.masking,
    b.enrollment_count,
    b.enrollment_type,
    b.conditions,
    b.keywords,
    b.interventions,
    b.arm_groups,
    b.eligibility_criteria,
    b.eligibility_sex,
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

    -- Entity linking: primary = queried_drug_name, fallback = fuzzy title match
    m.molecule_id,

    -- Drug name from the original API query; exposed for PostgREST consumers to verify linking
    b.queried_drug_name,

    -- Source tracking
    b.id AS bronze_id,
    b.created_at AS ingested_at,
    NOW() AS created_at,
    NOW() AS updated_at

FROM mol_bronze.clinicaltrials b
LEFT JOIN LATERAL (
    SELECT mol.molecule_id
    FROM mol_silver.molecules mol
    WHERE mol.needs_review = FALSE
      AND (
        -- Primary: match on the drug name that was used in the original API query
        (b.queried_drug_name IS NOT NULL AND LOWER(b.queried_drug_name) LIKE '%' || mol.canonical_name || '%')
        -- Fallback: fuzzy match in trial titles / interventions
        OR b.brief_title ILIKE '%' || mol.canonical_name || '%'
        OR b.official_title ILIKE '%' || mol.canonical_name || '%'
        OR EXISTS (
            SELECT 1 FROM jsonb_array_elements_text(b.interventions) elem
            WHERE elem ILIKE '%' || mol.canonical_name || '%'
        )
      )
    -- Priority: exact queried name > partial queried name > fuzzy match; then most specific (longest) drug name
    ORDER BY
        CASE WHEN b.queried_drug_name IS NOT NULL AND LOWER(b.queried_drug_name) = mol.canonical_name THEN 0
             WHEN b.queried_drug_name IS NOT NULL AND LOWER(b.queried_drug_name) LIKE '%' || mol.canonical_name || '%' THEN 1
             ELSE 2 END,
        LENGTH(mol.canonical_name) DESC,
        mol.resolution_confidence DESC
    LIMIT 1
) m ON TRUE
WHERE b.nct_id IS NOT NULL;
